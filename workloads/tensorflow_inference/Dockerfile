# Copyright (c) 2018 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# Building Tensorflow 1.10.0 with MKL support
FROM centos:7 AS tensorflow

# Tensorflow build dependencies
RUN yum install -y wget git which
RUN yum groupinstall -y 'Development Tools'
RUN yum install -y epel-release
RUN yum install -y python36 python36-devel
RUN yum install -y java-devel
# Install pip3.6
RUN python3.6 -m ensurepip --default-pip
RUN pip3.6 install \
    six \
    numpy \
    wheel
RUN wget https://github.com/bazelbuild/bazel/releases/download/0.15.2/bazel-0.15.2-installer-linux-x86_64.sh
RUN bash /bazel-0.15.2-installer-linux-x86_64.sh

# Env variables that configure tensorflow build
ENV CI_BUILD_PYTHON python3.6
ENV TF_NEED_CUDA 0
ENV TF_NEED_MKL 1

# Build tensorflow .whl package
RUN git clone https://github.com/tensorflow/tensorflow
RUN cd /tensorflow && \
    git checkout tags/v1.10.1 && \
    tensorflow/tools/ci_build/builds/configured CPU && \
    bazel build --config=mkl --config=opt //tensorflow/tools/pip_package:build_pip_package && \
    bazel-bin/tensorflow/tools/pip_package/build_pip_package /output

ADD /workloads/tensorflow_inference/prep_dataset_fruits.py /prep_dataset_fruits.py
ADD /workloads/tensorflow_inference/requirements.txt /requirements.txt
ADD /kaggle.json /root/.kaggle/kaggle.json
RUN pip3.6 install -r requirements.txt
RUN python3.6 /prep_dataset_fruits.py


# Building final container with workload
FROM centos:7

# Install Python 3.6
RUN yum install -y epel-release
RUN yum install -y python36

# Install pip3.6
RUN python3.6 -m ensurepip --default-pip

# Install TensorFlow with its dependencies
COPY --from=tensorflow /output /tensorflow-pkg
RUN pip3.6 install \
    wheel \
    h5py \
    pillow \
    /tensorflow-pkg/*.whl

# Cleanup wheel and tensorflow package after install
RUN pip3.6 uninstall -y wheel
RUN rm -rf /tensorflow-pkg

# Add and run resnet50 weights loading script
ADD /workloads/tensorflow_inference/load_nn_weights.py /load_nn_weights.py
RUN python3.6 load_nn_weights.py

# Add workload dataset and workload script
COPY --from=tensorflow /tensorflow-inference/fruits-360 /fruits-360
ADD /workloads/tensorflow_inference/inference /usr/local/bin/inference
RUN chmod +x /usr/local/bin/inference

# Add workload wrapper
ADD //dist/wrapper.pex /wrapper.pex

