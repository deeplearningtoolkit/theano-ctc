import numpy as np
import theano
import theano.tensor as T
from theano.gof import Op
from theano.gradient import grad_undefined

import os

class CtcBase(Op):
  def __init__(self):
    super(CtcBase,self).__init__()

  ctcLibDir = os.environ["CTC_LIB"]

  def c_lib_dirs(self):
    return [os.path.join(self.ctcLibDir, "build")]

  def c_libraries(self):
    return ["warpctc"]

  def c_header_dirs(self):
    return [os.path.join(self.ctcLibDir, "include")]

  def c_headers(self):
    return ["<iostream>", "ctc.h"]

  def make_node(self, acts, labels, input_lengths):
    # Unless specified, assume all sequences have full sequence length, i.e. acts_.shape[0]
    if input_lengths == None:
      input_lengths = T.cast(acts.shape[0], dtype="int32") * T.ones_like(acts[0,:,0], dtype=np.int32)

    # acts.shape = [seqLen, batchN, outputUnit]
    if acts.dtype != "float32":
      raise Exception("acts must be float32 instead of %s" % acts.dtype)
    # labels.shape = [batchN, labelLen]
    if labels.dtype != "int32":
      raise Exception("labels must be int32 instead of %s" % labels.dtype)
    # input_lengths.shape = [batchN]
    if input_lengths.dtype != "int32":
      raise Exception("input_lengths must be int32 instead of %s" % input_lengths.dtype)

    applyNode = theano.Apply(self, inputs=[acts, input_lengths, labels], outputs=[self.costs, self.gradients])

    # Return only the cost. Gradient will be returned by grad()
    self.default_output = 0 

    return applyNode

  def grad(self, inputs, output_grads):
    # self.gradients.shape = [seqLen, batchSize, outputSize]
    # output_grads[0].shape = [batchSize]  (one cost per sequence)
    # So, reshape output_grads to [1, batchSize, 1] for broadcasting
    output_grad = output_grads[0].reshape( (1, -1, 1) )
    return [output_grad * self.gradients,
            grad_undefined(self, 1, inputs[1]),
            grad_undefined(self, 2, inputs[2])]

  def c_support_code(self):
    return """

template <typename T>  // A smart pointer for new/delete
struct SmartPtr {
  T ptr;  
  SmartPtr() : ptr(0) {}
  SmartPtr(T p) : ptr(p) {}
  SmartPtr& operator= (T p) { ptr = p; return *this; }
  operator T() { return ptr; }
  ~SmartPtr() {     
    if (ptr != 0)  {
      delete[] ptr;
    }
  }
};

void flattenLabels(PyArrayObject* labelMatrix, SmartPtr<int*> &flatLabels, SmartPtr<int*>& labelT) {
  int m = PyArray_DIMS(labelMatrix)[0];
  int n = PyArray_DIMS(labelMatrix)[1];

  flatLabels = new int[ m * n ];  // allocate max size; okay if not filled
  labelT = new int[m];

  int f = 0;
  for (int i = 0; i < m; ++i) {
    int count = 0;
    for (int j = 0; j < n; ++j) {
      int label = *((int*)PyArray_GETPTR2(labelMatrix, i, j));
      if (label >= 0) {
        flatLabels[f++] = label;
        ++count;
      }
    }
    labelT[i] = count;
  }
}

// Ensure contiguous memory layout (no strides)
void createContiguousInputLengths(PyArrayObject* inputLengthsArray, SmartPtr<int*>& inputLengths) {
  int m = PyArray_DIMS(inputLengthsArray)[0];

  inputLengths = new int[m];

  for (int i = 0; i < m; ++i) {
    inputLengths[i] = *((int*)PyArray_GETPTR1(inputLengthsArray, i));
  }
}

    """
