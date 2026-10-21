
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Validate Compose') {
            steps {
                bat 'docker compose config --quiet'
            }
        }

        stage('Build Docker Images') {
            steps {
                bat 'docker compose build api frontend'
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
