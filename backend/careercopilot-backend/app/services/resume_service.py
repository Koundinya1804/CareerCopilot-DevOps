"""
app/services/resume_service.py
──────────────────────────────
Resume service: coordinates the full analysis pipeline.

  upload_resume()      → validate, store in S3/local, create DB record
  analyse_resume()     → parse PDF → extract entities → ATS score → Gemini → persist
  get_report()         → fetch CareerReport by ID
  list_resumes()       → all resumes for a user
  set_primary()        → mark one resume as primary
  delete_resume()      → remove from DB (S3 cleanup deferred to background task)
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.resume_agent import run_resume_analysis
from app.core.llm_provider import get_last_call_usage
from app.models.agent_log import AgentName
from app.services.agent_log_service import timed_agent_call
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.resume import CareerReport, Resume, ResumeStatus, SeniorityMatch
from app.models.notification import NotificationType
from app.services.notification_service import notify
from app.utils.ats_scorer import calculate_ats_score
from app.utils.nlp_extractor import extract_entities
from app.utils.pdf_parser import clean_text, extract_text

logger = get_logger(__name__)

# Local fallback storage dir (used when S3 not configured)
_LOCAL_UPLOAD_DIR = Path("uploads")
_LOCAL_UPLOAD_DIR.mkdir(exist_ok=True)

# Allowed MIME types
ALLOWED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}


class ResumeService:

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Upload ─────────────────────────────────────────────────────────────────
    async def upload_resume(
        self,
        user_id:     int,
        file:        UploadFile,
        make_primary: bool = True,
    ) -> Resume:
        """
        Validate the uploaded file, store it, and create a DB record.
        Does NOT trigger analysis — call analyse_resume() separately.
        """
        # Validate MIME
        mime = (file.content_type or "").lower()
        if mime not in ALLOWED_MIMES:
            raise ValidationError(
                f"File type '{mime}' is not supported. Upload a PDF or DOCX file."
            )

        # Read file into memory
        file_bytes = await file.read()
        size = len(file_bytes)

        if size > settings.MAX_RESUME_SIZE_BYTES:
            raise ValidationError(
                f"File size {size / 1024 / 1024:.1f} MB exceeds the {settings.MAX_RESUME_SIZE_MB} MB limit."
            )
        if size < 1000:
            raise ValidationError("File appears to be empty or too small to be a valid resume.")

        # Generate storage key
        file_ext = Path(file.filename or "resume.pdf").suffix.lower() or ".pdf"
        unique_key = f"resumes/{user_id}/{uuid.uuid4()}{file_ext}"

        # Store file
        s3_key = await self._store_file(file_bytes, unique_key, mime)

        # If making primary, demote existing primary
        if make_primary:
            self._db.query(Resume).filter(
                Resume.user_id == user_id,
                Resume.is_primary == 1,
            ).update({"is_primary": 0})

        resume = Resume(
            user_id=user_id,
            filename=file.filename or f"resume{file_ext}",
            s3_key=s3_key,
            file_size_bytes=size,
            mime_type=mime,
            status=ResumeStatus.UPLOADED,
            is_primary=1 if make_primary else 0,
        )
        self._db.add(resume)
        self._db.flush()

        logger.info("resume_uploaded", resume_id=resume.resume_id, user_id=user_id, size=size)
        return resume

    # ── Analysis Pipeline ──────────────────────────────────────────────────────
    async def analyse_resume(
        self,
        resume_id:   int,
        user_id:     int,
        target_role: str | None = None,
    ) -> CareerReport:
        """
        Full analysis pipeline:
          load bytes → extract text → NLP entities → ATS score → Gemini → persist
        """
        resume = self._get_resume_or_404(resume_id, user_id)

        # Mark as processing
        resume.status = ResumeStatus.PROCESSING
        self._db.flush()

        try:
            # 1. Load file bytes
            file_bytes = await self._load_file(resume.s3_key)

            # 2. Extract text
            logger.info("resume_text_extraction_start", resume_id=resume_id)
            parsed = extract_text(file_bytes, resume.mime_type)
            if parsed.is_empty:
                raise ValidationError(
                    "Could not extract readable text from the resume. "
                    "Ensure the PDF is not scanned/image-only."
                )
            clean = clean_text(parsed.raw_text)

            # Cache raw text on resume record
            resume.raw_text   = clean[:65535]   # TEXT column limit
            resume.page_count = parsed.page_count

            # 3. NLP entity extraction (rule-based, fast)
            logger.info("resume_nlp_extraction_start", resume_id=resume_id)
            entities = extract_entities(clean, parsed.sections)

            # 4. ATS scoring (rule-based, deterministic)
            logger.info("resume_ats_scoring_start", resume_id=resume_id)
            ats_result = calculate_ats_score(
                parsed_text=clean,
                entities=entities,
                sections=parsed.sections,
                word_count=parsed.word_count,
                page_count=parsed.page_count,
                target_role=target_role,
            )

            # 5. AI enrichment (Groq by default — see app/core/llm_provider.py)
            logger.info("resume_ai_analysis_start", resume_id=resume_id)
            with timed_agent_call(
                self._db, user_id=user_id, agent_name=AgentName.RESUME_ANALYSER,
                metadata={"resume_id": resume_id, "target_role": target_role},
            ) as ctx:
                ai_result = run_resume_analysis(
                    resume_text=clean,
                    entities=entities,
                    ats_result=ats_result,
                    page_count=parsed.page_count,
                    word_count=parsed.word_count,
                    target_role=target_role,
                )
                usage = get_last_call_usage()
                ctx["input_tokens"]  = usage.get("input_tokens")
                ctx["output_tokens"] = usage.get("output_tokens")

            # 6. Persist report
            report = CareerReport(
                user_id=user_id,
                resume_id=resume_id,

                ats_score=ai_result.ats_score,
                formatting_score=ai_result.formatting_score,
                content_score=ai_result.content_score,
                keyword_score=ai_result.keyword_score,
                experience_score=ai_result.experience_score,

                total_skills_found=len(ai_result.skills),
                skills_matched=len(ai_result.keywords_found),
                skills_missing=len(ai_result.keywords_missing),

                extracted_skills=ai_result.skills,
                extracted_projects=ai_result.projects,
                extracted_certs=ai_result.certifications,
                extracted_education=ai_result.education,
                extracted_experience=ai_result.experience,
                contact_info=ai_result.contact_info,

                summary=ai_result.summary,
                strengths=ai_result.strengths,
                improvements=ai_result.improvements,
                keywords_found=ai_result.keywords_found,
                keywords_missing=ai_result.keywords_missing,
                seniority_match=SeniorityMatch(ai_result.seniority_match),

                model_used=ai_result.model_used,
                tokens_consumed=ai_result.tokens_consumed,
                processing_time_ms=ai_result.processing_time_ms,
            )
            self._db.add(report)

            resume.status = ResumeStatus.ANALYSED
            self._db.flush()

            notify(
                self._db,
                user_id=user_id,
                type=NotificationType.RESUME_ANALYSIS_COMPLETED,
                title="Resume analysis complete",
                message=f"Your resume scored {ai_result.ats_score}/100 on ATS compatibility.",
                action_url=f"/resume/{resume_id}/report",
            )

            logger.info(
                "resume_analysis_persisted",
                resume_id=resume_id,
                report_id=report.report_id,
                ats_score=ai_result.ats_score,
                ms=ai_result.processing_time_ms,
            )
            return report

        except Exception as exc:
            resume.status = ResumeStatus.FAILED
            self._db.flush()
            logger.error("resume_analysis_failed", resume_id=resume_id, error=str(exc))
            raise

    # ── Queries ────────────────────────────────────────────────────────────────
    def get_report(self, report_id: int, user_id: int) -> CareerReport:
        report = self._db.scalar(
            select(CareerReport).where(
                CareerReport.report_id == report_id,
                CareerReport.user_id   == user_id,
            )
        )
        if not report:
            raise NotFoundError("CareerReport", report_id)
        return report

    def get_latest_report(self, resume_id: int, user_id: int) -> CareerReport | None:
        return self._db.scalar(
            select(CareerReport)
            .where(
                CareerReport.resume_id == resume_id,
                CareerReport.user_id   == user_id,
            )
            .order_by(CareerReport.created_at.desc())
            .limit(1)
        )

    def get_latest_reports_for_resumes(
        self, resume_ids: list[int], user_id: int
    ) -> dict[int, CareerReport]:
        """
        Batched version of get_latest_report() — one query for N resumes
        instead of N queries. Used by list_resumes() to avoid an N+1 (was:
        one get_latest_report() call per resume in a Python loop).
        Returns {resume_id: most_recent_CareerReport}.
        """
        if not resume_ids:
            return {}
        rows = self._db.scalars(
            select(CareerReport)
            .where(
                CareerReport.resume_id.in_(resume_ids),
                CareerReport.user_id == user_id,
            )
            .order_by(CareerReport.resume_id, CareerReport.created_at.desc())
        ).all()
        latest_by_resume: dict[int, CareerReport] = {}
        for report in rows:
            # Rows come back grouped by resume_id (ORDER BY resume_id first),
            # newest first within each group — keep only the first one seen.
            if report.resume_id not in latest_by_resume:
                latest_by_resume[report.resume_id] = report
        return latest_by_resume

    def list_resumes(self, user_id: int) -> list[Resume]:
        return list(
            self._db.scalars(
                select(Resume)
                .where(Resume.user_id == user_id)
                .order_by(Resume.created_at.desc())
            ).all()
        )

    def set_primary(self, resume_id: int, user_id: int) -> Resume:
        self._db.query(Resume).filter(
            Resume.user_id == user_id, Resume.is_primary == 1
        ).update({"is_primary": 0})
        resume = self._get_resume_or_404(resume_id, user_id)
        resume.is_primary = 1
        self._db.flush()
        return resume

    def delete_resume(self, resume_id: int, user_id: int) -> None:
        resume = self._get_resume_or_404(resume_id, user_id)
        self._db.delete(resume)
        self._db.flush()
        logger.info("resume_deleted", resume_id=resume_id, user_id=user_id)

    # ── Internal helpers ───────────────────────────────────────────────────────
    def _get_resume_or_404(self, resume_id: int, user_id: int) -> Resume:
        resume = self._db.scalar(
            select(Resume).where(
                Resume.resume_id == resume_id,
                Resume.user_id   == user_id,
            )
        )
        if not resume:
            raise NotFoundError("Resume", resume_id)
        return resume

    async def _store_file(self, data: bytes, key: str, mime: str) -> str:
        """Store file in S3 or local filesystem fallback."""
        if settings.AWS_ACCESS_KEY_ID and not settings.AWS_ACCESS_KEY_ID.startswith("CHANGE"):
            return await self._store_s3(data, key, mime)
        return self._store_local(data, key)

    async def _store_s3(self, data: bytes, key: str, mime: str) -> str:
        import boto3  # type: ignore[import]
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
            **({"endpoint_url": settings.S3_ENDPOINT_URL} if settings.S3_ENDPOINT_URL else {}),
        )
        s3.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
            Body=data,
            ContentType=mime,
            ServerSideEncryption="AES256",
        )
        logger.info("file_stored_s3", key=key, size=len(data))
        return key

    def _store_local(self, data: bytes, key: str) -> str:
        local_path = _LOCAL_UPLOAD_DIR / key.replace("/", "_")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        logger.info("file_stored_local", path=str(local_path))
        return key

    async def _load_file(self, s3_key: str) -> bytes:
        """Load file from S3 or local fallback."""
        if settings.AWS_ACCESS_KEY_ID and not settings.AWS_ACCESS_KEY_ID.startswith("CHANGE"):
            return await self._load_s3(s3_key)
        return self._load_local(s3_key)

    async def _load_s3(self, key: str) -> bytes:
        import boto3  # type: ignore[import]
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
            **({"endpoint_url": settings.S3_ENDPOINT_URL} if settings.S3_ENDPOINT_URL else {}),
        )
        obj = s3.get_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
        return obj["Body"].read()

    def _load_local(self, key: str) -> bytes:
        local_path = _LOCAL_UPLOAD_DIR / key.replace("/", "_")
        if not local_path.exists():
            raise NotFoundError("Resume file", key)
        return local_path.read_bytes()
