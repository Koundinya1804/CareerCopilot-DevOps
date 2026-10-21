
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    environment {
        MYSQL_PASSWORD = 'ci-placeholder-not-for-deployment'
        MYSQL_ROOT_PASSWORD = 'ci-placeholder-not-for-deployment'
    }

    stages {
        stage('Validate Compose') {
            steps {
                sh 'docker compose config --quiet'
            }
        }

        stage('Build Docker Images') {
            steps {
                sh 'docker compose build api frontend'
            }
        }
    }

    post {
        success {
            echo 'CareerCopilot CI pipeline completed successfully.'
        }
        failure {
            echo 'Pipeline failed. Review the stage logs above.'
        }
    }
}
