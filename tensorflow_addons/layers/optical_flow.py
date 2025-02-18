# Copyright 2019 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Tensorflow op performing correlation cost operation."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
from tensorflow_addons.utils import keras_utils
from tensorflow_addons.utils.resource_loader import get_path_to_datafile

_correlation_cost_op_so = tf.load_op_library(
    get_path_to_datafile("custom_ops/layers/_correlation_cost_ops.so"))


@tf.function
def _correlation_cost(input_a,
                      input_b,
                      kernel_size,
                      max_displacement,
                      stride_1,
                      stride_2,
                      pad,
                      data_format='channels_last',
                      name=None):
    """Correlation Cost Volume computation.

    "FlowNet: Learning Optical Flow with Convolutional Networks"
    Philipp Fischer, Alexey Dosovitskiy, Eddy Ilg, Philip Hausser,
    Caner Hazirbas, Vladimir Golkov, Patrick van der Smagt,
    Daniel Cremers, Thomas Brox. https://arxiv.org/abs/1504.06852

    Computes a cost volume using correlation for two inputs. For feature
    maps A, B with spatial dimensions w, h, c it computes

      output(a, b) = sum_{l in [-k,k]**2}  < I(a+l), J(b+l) >

    where the patches of size K=2d + 1 are centered in position a resp. b.

    The output shape is [B, C', H', W'], where

      r = max_displacement / stride_2;
      bd = max_displacement + (kernel_size - 1) / 2
      C' = (2 * r + 1) ** 2
      H' = H + 2 * (pad - bd) / stride_1
      W' = W + 2 * (pad - bd) / stride_1

    Note: When the data_format requests "channels_last", an additional explicit
      transpose operation is executed.

    Args:
      input_a: A `Tensor` of the format specified by `data_format`.
      input_b: A `Tensor` of the format specified by `data_format`.
      kernel_size: An integer specifying the height and width of the
          patch used to compute the per-patch costs.
      max_displacement: An integer specifying the maximum search radius
          for each position.
      stride_1: An integer specifying the stride length in the input.
      stride_2: An integer specifying the stride length in the patch.
      pad: An integer specifying the paddings in height and width.
      data_format: Specifies the data format.
          Possible values are:
          "channels_last" float [batch, height, width, channels]
          "channels_first" float [batch, channels, height, width]
          Defaults to `"channels_last"`.
      name: A name for the operation (optional).

    Returns:
      A `Tensor` of the format specified by `data_format`.
    """

    with tf.name_scope(name or "correlation_cost"):
        op_call = _correlation_cost_op_so.addons_correlation_cost

        if data_format == "channels_last":
            op_data_format = "NHWC"
        elif data_format == "channels_first":
            op_data_format = "NCHW"
        else:
            raise ValueError("`data_format` must be either `channels_last` or"
                             "`channels_first`")

        ret = op_call(
            input_a,
            input_b,
            kernel_size=kernel_size,
            max_displacement=max_displacement,
            stride_1=stride_1,
            stride_2=stride_2,
            pad=pad,
            data_format=op_data_format)
        if data_format == 'channels_last':
            # this is easier to maintain without
            # specializing an additional cuda kernel
            return tf.transpose(ret, [0, 2, 3, 1])
        return ret


@tf.RegisterGradient("Addons>CorrelationCost")
def _correlation_cost_grad(op, grad_output):
    kernel_size = op.get_attr("kernel_size")
    max_displacement = op.get_attr("max_displacement")
    stride_1 = op.get_attr("stride_1")
    stride_2 = op.get_attr("stride_2")
    pad = op.get_attr("pad")
    data_format = op.get_attr("data_format")

    input_a = tf.convert_to_tensor(op.inputs[0], name="input_a")
    input_b = tf.convert_to_tensor(op.inputs[1], name="input_b")
    grad_output_tensor = tf.convert_to_tensor(grad_output, name="grad_output")

    op_call = _correlation_cost_op_so.addons_correlation_cost_grad
    grads = op_call(
        input_a,
        input_b,
        grad_output_tensor,
        kernel_size=kernel_size,
        max_displacement=max_displacement,
        stride_1=stride_1,
        stride_2=stride_2,
        pad=pad,
        data_format=data_format)

    grad_input_a = tf.convert_to_tensor(grads[0], name="grad_input_a")
    grad_input_b = tf.convert_to_tensor(grads[1], name="grad_input_b")
    return [grad_input_a, grad_input_b]


@keras_utils.register_keras_custom_object
class CorrelationCost(tf.keras.layers.Layer):
    """Correlation Cost Layer.

    This layer implements the correlation operation from FlowNet Learning
    Optical Flow with Convolutional Networks (Fischer et al.):
    https://arxiv.org/abs/1504.06

    Args:
        kernel_size: An integer specifying the height and width of the
            patch used to compute the per-patch costs.
        max_displacement: An integer specifying the maximum search radius
            for each position.
        stride_1: An integer specifying the stride length in the input.
        stride_2: An integer specifying the stride length in the patch.
        pad: An integer specifying the paddings in height and width.
        data_format: Specifies the data format.
            Possible values are:
                "channels_last" float [batch, height, width, channels]
                "channels_first" float [batch, channels, height, width]
                Defaults to `"channels_last"`.
    """

    def __init__(self, kernel_size, max_displacement, stride_1, stride_2, pad,
                 data_format, **kwargs):
        self.kernel_size = kernel_size
        self.max_displacement = max_displacement
        self.stride_1 = stride_1
        self.stride_2 = stride_2
        self.pad = pad

        if data_format != "channels_last" and data_format != "channels_first":
            raise ValueError("`data_format` must be either `channels_last` or"
                             "`channels_first`, instead got %s" % data_format)

        self.data_format = data_format

        super(CorrelationCost, self).__init__(**kwargs)

    def build(self, input_shape):
        if not isinstance(input_shape, list):
            raise ValueError("Input must be a list of two Tensors to process")
        super(CorrelationCost, self).build(input_shape)

    def call(self, inputs):
        if not isinstance(inputs, list):
            raise ValueError("Input must be a list of two Tensors to process")

        input_a = tf.convert_to_tensor(inputs[0])
        input_b = tf.convert_to_tensor(inputs[1])

        return _correlation_cost(
            input_a,
            input_b,
            kernel_size=self.kernel_size,
            max_displacement=self.max_displacement,
            stride_1=self.stride_1,
            stride_2=self.stride_2,
            pad=self.pad,
            data_format=self.data_format)

    def compute_output_shape(self, input_shape):
        assert isinstance(input_shape, list)

        #  Input validation
        if len(input_shape) != 2:
            raise ValueError("Input must be a list of two shapes")

        for idx in range(4):
            if input_shape[0][idx] != input_shape[1][idx]:
                raise ValueError("Input shapes must match")

        n = input_shape[0][0]
        r = self.max_displacement // self.stride_2
        bd = self.max_displacement + (self.kernel_size - 1) // 2
        output_c = (2 * r + 1)**2

        if self.data_format == "channels_first":
            output_h = input_shape[0][2] + 2 * (self.pad - bd) // self.stride_1
            output_w = input_shape[0][3] + 2 * (self.pad - bd) // self.stride_1
            return [(n, output_c, output_h, output_w)]

        elif self.data_format == "channels_last":
            output_h = input_shape[0][1] + 2 * (self.pad - bd) // self.stride_1
            output_w = input_shape[0][2] + 2 * (self.pad - bd) // self.stride_1
            return [(n, output_h, output_w, output_c)]
        else:
            raise ValueError("`data_format` must be either `channels_last` or"
                             "`channels_first`")

    def get_config(self):
        config = {
            'kernel_size': self.kernel_size,
            'max_displacement': self.max_displacement,
            'stride_1': self.stride_1,
            'stride_2': self.stride_2,
            'pad': self.pad,
            'data_format': self.data_format
        }

        base_config = super(CorrelationCost, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))
