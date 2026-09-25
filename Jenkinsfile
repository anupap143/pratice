// Pipeline for practice-app on the kind cluster "mycluster" (test-pgsql, 172.16.30.124).
// Needs the custom Jenkins container with docker, kind and kubectl (see README, step 1).
pipeline {
    agent any

    options {
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 20, unit: 'MINUTES')
    }

    environment {
        APP          = 'practice-app'
        NAMESPACE    = 'practice'
        IMAGE        = "practice-app:${env.BUILD_NUMBER}"
        KIND_CLUSTER = 'mycluster'
        KUBECONFIG   = '/var/jenkins_home/kubeconfig'
    }

    stages {
        stage('Check tools') {
            steps {
                sh '''
                  docker version --format 'Docker {{.Server.Version}}'
                  kind version
                  kubectl version --client
                  kubectl get nodes
                '''
            }
        }

        stage('Unit tests') {
            steps {
                // Builds only the "test" stage of the Dockerfile; pytest runs inside it.
                sh 'docker build --target test -t $APP:test-$BUILD_NUMBER .'
            }
            post {
                always { sh 'docker rmi -f $APP:test-$BUILD_NUMBER || true' }
            }
        }

        stage('Build image') {
            steps {
                sh 'docker build --target runtime -t $IMAGE .'
            }
        }

        stage('Load image into kind') {
            steps {
                sh 'kind load docker-image $IMAGE --name $KIND_CLUSTER'
            }
        }

        stage('Deploy') {
            steps {
                sh '''
                  kubectl apply -f k8s/namespace.yaml
                  kubectl apply -f k8s/configmap.yaml -f k8s/service.yaml

                  sed -e "s|IMAGE_PLACEHOLDER|$IMAGE|" \
                      -e "s|VERSION_PLACEHOLDER|$BUILD_NUMBER|" \
                      k8s/deployment.yaml | kubectl apply -f -

                  # Only apply the Ingress if an nginx ingress controller is installed
                  if kubectl get ingressclass nginx >/dev/null 2>&1; then
                    kubectl apply -f k8s/ingress.yaml
                  else
                    echo "No nginx IngressClass found, skipping k8s/ingress.yaml"
                  fi

                  kubectl -n $NAMESPACE rollout status deployment/$APP --timeout=180s
                  kubectl -n $NAMESPACE get pods -l app=$APP -o wide
                '''
            }
            post {
                failure {
                    sh '''
                      echo "Rollout failed, rolling back to the previous version"
                      kubectl -n $NAMESPACE describe deployment/$APP | tail -n 25 || true
                      kubectl -n $NAMESPACE get events --sort-by=.lastTimestamp | tail -n 15 || true
                      kubectl -n $NAMESPACE rollout undo deployment/$APP || true
                    '''
                }
            }
        }

        stage('Smoke test') {
            steps {
                // Calls the Service from inside the cluster, like another app would.
                sh '''
                  kubectl -n $NAMESPACE run smoke-$BUILD_NUMBER --rm -i --restart=Never \
                    --image=curlimages/curl:8.10.1 -- \
                    curl -fsS --retry 5 --retry-delay 2 --retry-all-errors http://$APP/api/info
                '''
            }
        }
    }

    post {
        success {
            echo "Deployed ${IMAGE} to namespace ${NAMESPACE}."
        }
        always {
            // Remove dangling build layers so the server disk doesn't fill up
            sh 'docker image prune -f || true'
        }
    }
}
