# Copyright 2019 The TensorFlow Authors. All Rights Reserved.
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
# ==============================================================================

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
from tensorflow_addons.utils import keras_utils
from tensorflow_addons.utils.resource_loader import get_path_to_datafile

_activation_ops_so = tf.load_op_library(
    get_path_to_datafile("custom_ops/activations/_activation_ops.so"))


@keras_utils.register_keras_custom_object
@tf.function
def mish(x):
    """Mish: A Self Regularized Non-Monotonic Neural Activation Function.

    Computes mish activation: x * tanh(softplus(x))

    See [Mish: A Self Regularized Non-Monotonic Neural Activation Function](https://arxiv.org/abs/1908.08681).

    Args:
        x: A `Tensor`. Must be one of the following types:
            `float16`, `float32`, `float64`.
    Returns:
        A `Tensor`. Has the same type as `x`.
    """
    x = tf.convert_to_tensor(x)
    return _activation_ops_so.addons_mish(x)


@tf.RegisterGradient("Addons>Mish")
def _mish_grad(op, grad):
    return _activation_ops_so.addons_mish_grad(grad, op.inputs[0])
