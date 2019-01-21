pipeline {
    agent any
    environment {
        DOCKER_REPOSITORY_URL = credentials('DOCKER_REPOSITORY_URL')
    }
    stages{
        stage("Flake8 formatting scan") {
            steps {
                sh '''
                  pip3 install --user tox==3.5.2
                  tox -e flake8
                '''
            }
        }
        stage("Run unit tests suite") {
            steps {
                sh '''
                  pip3 install --user tox==3.5.2
                  tox -e unit
                '''
            }
        }
        stage("Build OWCA pex file") {
            steps {
                sh '''
                  pip3 install --user tox==3.5.2
                  tox -e owca_package
                '''
                stash(name: "owca", includes: "dist/**")
                archiveArtifacts(artifacts: "dist/**")
            }
            post {
                always {
                    sh '''
                    rm -fr dist
                    '''
                }
            }
        }
        stage("Build wrappers pex files") {
            steps {
                sh '''
                  pip3 install --user tox==3.5.2
                  tox -e wrapper_package
                '''
                stash(name: "wrappers", includes: "dist/**")
                archiveArtifacts(artifacts: "dist/**")
            }
            post {
                always {
                    sh '''
                    rm -fr dist
                    '''
                }
            }
        }
        stage("Building Docker images in parallel") {
            parallel {
                stage("Build and push Redis Docker image") {
                    steps {
                        sh '''
                        IMAGE_NAME=${DOCKER_REPOSITORY_URL}/owca/redis:${GIT_COMMIT}
                        docker build -t ${IMAGE_NAME} -f ${WORKSPACE}/workloads/redis/Dockerfile ${WORKSPACE}
                        docker push ${IMAGE_NAME}
                        '''
                    }
                }
                stage("Build and push stress-ng Docker image") {
                    steps {
                        unstash("wrappers")
                        sh '''
                        IMAGE_NAME=${DOCKER_REPOSITORY_URL}/owca/stress_ng:${GIT_COMMIT}
                        docker build -t ${IMAGE_NAME} -f ${WORKSPACE}/workloads/stress_ng/Dockerfile ${WORKSPACE}
                        docker push ${IMAGE_NAME}
                        '''
                    }
                }
                stage("Build and push rpc-perf Docker image") {
                    steps {
                        unstash("wrappers")
                        sh '''
                        IMAGE_NAME=${DOCKER_REPOSITORY_URL}/owca/rpc_perf:${GIT_COMMIT}
                        docker build -t ${IMAGE_NAME} -f ${WORKSPACE}/workloads/rpc_perf/Dockerfile ${WORKSPACE}
                        docker push ${IMAGE_NAME}
                        '''
                    }
                }
                stage("Build and push Tensorflow training Docker image") {
                    steps {
                        withCredentials([file(credentialsId: 'kaggle.json', variable: 'KAGGLE_JSON')]) {
                            unstash("wrappers")
                            sh '''
                            cp -f ${KAGGLE_JSON} kaggle.json
                            IMAGE_NAME=${DOCKER_REPOSITORY_URL}/owca/tensorflow_train:${GIT_COMMIT}
                            docker build -t ${IMAGE_NAME} -f ${WORKSPACE}/workloads/tensorflow_train/Dockerfile ${WORKSPACE}
                            docker push ${IMAGE_NAME}
                            '''
                        }
                    }
                    post {
                        always {
                            sh '''
                            rm -f kaggle.json
                            '''
                        }
                    }
                }
                stage("Build and push Tensorflow inference Docker image") {
                    steps {
                        withCredentials([file(credentialsId: 'kaggle.json', variable: 'KAGGLE_JSON')]) {
                            unstash("wrappers")
                            sh '''
                            cp -f ${KAGGLE_JSON} kaggle.json
                            IMAGE_NAME=${DOCKER_REPOSITORY_URL}/owca/tensorflow_inference:${GIT_COMMIT}
                            docker build -t ${IMAGE_NAME} -f ${WORKSPACE}/workloads/tensorflow_inference/Dockerfile ${WORKSPACE}
                            docker push ${IMAGE_NAME}
                            '''
                        }
                    }
                    post {
                        always {
                            sh '''
                            rm -f kaggle.json
                            '''
                        }
                    }
                }
                stage("Build and push Twemcache Docker image") {
                    steps {
                        sh '''
                        IMAGE_NAME=${DOCKER_REPOSITORY_URL}/owca/twemcache:${GIT_COMMIT}
                        docker build -t ${IMAGE_NAME} -f ${WORKSPACE}/workloads/twemcache/Dockerfile ${WORKSPACE}
                        docker push ${IMAGE_NAME}
                        '''
                    }
                }
                stage("Build and push YCSB Docker image") {
                    steps {
                        unstash("wrappers")
                        sh '''
                        IMAGE_NAME=${DOCKER_REPOSITORY_URL}/owca/ycsb:${GIT_COMMIT}
                        docker build -t ${IMAGE_NAME} -f ${WORKSPACE}/workloads/ycsb/Dockerfile ${WORKSPACE}
                        docker push ${IMAGE_NAME}
                        '''
                    }
                }
                stage("Build and push Cassandra Stress Docker image") {
                    steps {
                        unstash("wrappers")
                        sh '''
                        IMAGE_NAME=${DOCKER_REPOSITORY_URL}/owca/cassandra_stress:${GIT_COMMIT}
                        docker build -t ${IMAGE_NAME} -f ${WORKSPACE}/workloads/cassandra_stress/Dockerfile ${WORKSPACE}
                        docker push ${IMAGE_NAME}
                        '''
                    }
                }
                stage("Build and push Tensorflow Benchmark Docker image") {
                    steps {
                        unstash("wrappers")
                        sh '''
                        IMAGE_NAME=${DOCKER_REPOSITORY_URL}/owca/tensorflow_benchmark:${GIT_COMMIT}
                        docker build -t ${IMAGE_NAME} -f ${WORKSPACE}/workloads/tensorflow_benchmark/Dockerfile ${WORKSPACE}
                        docker push ${IMAGE_NAME}
                        '''
                    }
                }
                stage("Build and push mutilate Docker image") {
                    steps {
                        unstash("wrappers")
                        sh '''
                        IMAGE_NAME=${DOCKER_REPOSITORY_URL}/owca/mutilate:${GIT_COMMIT}
                        docker build -t ${IMAGE_NAME} -f ${WORKSPACE}/workloads/mutilate/Dockerfile ${WORKSPACE}
                        docker push ${IMAGE_NAME}
                        '''
                    }
                }
                stage("Build and push SpecJBB Docker image") {
                    steps {
                        withCredentials([file(credentialsId: 'specjbb', variable: 'SPECJBB_TAR')]) {
                            unstash("wrappers")
                            sh '''
                            cp ${SPECJBB_TAR} ${WORKSPACE}/workloads/specjbb
                            tar -xC ${WORKSPACE}/workloads/specjbb -f ${WORKSPACE}/workloads/specjbb/specjbb.tar.bz2
                            IMAGE_NAME=${DOCKER_REPOSITORY_URL}/owca/specjbb:${GIT_COMMIT}
                            docker build -t ${IMAGE_NAME} -f ${WORKSPACE}/workloads/specjbb/Dockerfile ${WORKSPACE}
                            docker push ${IMAGE_NAME}
                            '''
                        }
                    }
                    post {
                        always {
                            sh '''
                            rm -rf ${WORKSPACE}/workloads/specjbb/specjbb.tar.bz2 ${WORKSPACE}/workloads/specjbb/specjbb
                            '''
                        }
                    }
                }
            }
        }
    }
}
