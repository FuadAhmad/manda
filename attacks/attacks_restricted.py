from __future__ import division, absolute_import, print_function

from collections import defaultdict
import numpy as np
import tensorflow.compat.v1 as tf
from tqdm import tqdm
from cleverhans.utils import other_classes
from cleverhans.utils_tf import batch_eval, model_argmax
from cleverhans.attacks import SaliencyMapMethod

# define the feature groups that we can manipulate or not
modified_fea = {'nsl-kdd': [1, 5, 6, 10, 11, 13, 16, 17, 18, 19] + list(range(23, 42)),
                'cicids': list(range(1, 30)) + list(range(34, 43)) + list(range(51, 56)) + list(range(62, 66))}

unmodified_fea = {'nsl-kdd':  list(set(list(range(121))) - set(modified_fea['nsl-kdd'])),
                  'cicids': list(set(list(range(81))) - set(modified_fea['cicids']))}


def fgsm(x, predictions, eps, modified_percentage, clip_min=None, clip_max=None, y=None):
    """
    Computes symbolic TF tensor for the adversarial samples. This must
    be evaluated with a session.run call.
    :param x: the input placeholder
    :param predictions: the model's output tensor
    :param eps: the epsilon (input variation parameter)
    :param clip_min: optional parameter that can be used to set a minimum
                    value for components of the example returned
    :param clip_max: optional parameter that can be used to set a maximum
                    value for components of the example returned
    :param y: the output placeholder. Use None (the default) to avoid the
            label leaking effect.
    :return: a tensor for the adversarial example
    """
    multiplier = np.ones([1, 121])
    for i in range(121):
        if i in unmodified_fea['nsl-kdd']:
            multiplier[0, i] = 0.0
    multiplier = tf.constant(value=multiplier, dtype=tf.float32)
    # multiplier =1

    # Compute loss
    if y is None:
        # In this case, use model predictions as ground truth
        y = tf.to_float(
            tf.equal(predictions,
                     tf.reduce_max(predictions, 1, keep_dims=True)))
    y = y / tf.reduce_sum(y, 1, keep_dims=True)
    logits, _ = predictions.op.inputs
    loss = tf.reduce_mean(
        tf.nn.softmax_cross_entropy_with_logits(logits=logits, labels=y)
    )

    # Define gradient of loss wrt input
    grad, = tf.gradients(loss, x)

    # Take sign of gradient (nullify the sign for the features that is not eligible to modify)
    signed_grad = tf.sign(grad)
    signed_grad = multiplier * signed_grad

    # Multiply by constant epsilon
    scaled_signed_grad = eps * signed_grad

    # get the clip upper-bound and lower bound
    lower_bound = x - (clip_max - clip_min) * 0.001
    upper_bound = x + (clip_max - clip_min) * modified_percentage
    c_min = tf.maximum(tf.constant(value=clip_min, dtype='float32'), lower_bound)
    c_max = tf.minimum(tf.constant(value=clip_max, dtype='float32'), upper_bound)
    # c_min = clip_min
    # c_max = clip_max

    # Add perturbation to original example to obtain adversarial example
    adv_x = tf.stop_gradient(x + scaled_signed_grad)

    # If clipping is needed, reset all values outside of [clip_min, clip_max]
    if (clip_min is not None) and (clip_max is not None):
        adv_x = tf.clip_by_value(adv_x, c_min, c_max)

    return adv_x


def fgsm_cicids(x, predictions, eps, modified_percentage, clip_min=None, clip_max=None, y=None):
    """
    Computes symbolic TF tensor for the adversarial samples. This must
    be evaluated with a session.run call.
    :param x: the input placeholder
    :param predictions: the model's output tensor
    :param eps: the epsilon (input variation parameter)
    :param clip_min: optional parameter that can be used to set a minimum
                    value for components of the example returned
    :param clip_max: optional parameter that can be used to set a maximum
                    value for components of the example returned
    :param y: the output placeholder. Use None (the default) to avoid the
            label leaking effect.
    :return: a tensor for the adversarial example
    """
    multiplier = np.ones(81)
    for i in range(81):
        if i in unmodified_fea['cicids']:
            multiplier[i] = 0.0
    multiplier = multiplier.reshape((9, 9, 1))
    multiplier = tf.constant(value=multiplier, dtype=tf.float32)

    # Compute loss
    if y is None:
        # In this case, use model predictions as ground truth
        y = tf.to_float(
            tf.equal(predictions,
                     tf.reduce_max(predictions, 1, keep_dims=True)))
    y = y / tf.reduce_sum(y, 1, keep_dims=True)
    logits, _ = predictions.op.inputs
    loss = tf.reduce_mean(
        tf.nn.softmax_cross_entropy_with_logits(logits=logits, labels=y)
    )

    # Define gradient of loss wrt input
    grad, = tf.gradients(loss, x)

    # Take sign of gradient (nullify the sign for the features that is not eligible to modify)
    signed_grad = tf.sign(grad)
    signed_grad = multiplier * signed_grad

    # Multiply by constant epsilon
    scaled_signed_grad = eps * signed_grad

    # get the clip upper-bound and lower bound
    lower_bound = x - (clip_max - clip_min) * 0.001
    upper_bound = x + (clip_max - clip_min) * modified_percentage
    c_min = tf.maximum(tf.constant(value=clip_min, dtype='float32'), lower_bound)
    c_max = tf.minimum(tf.constant(value=clip_max, dtype='float32'), upper_bound)

    # Add perturbation to original example to obtain adversarial example
    adv_x = tf.stop_gradient(x + scaled_signed_grad)

    # If clipping is needed, reset all values outside of [clip_min, clip_max]
    if (clip_min is not None) and (clip_max is not None):
        adv_x = tf.clip_by_value(adv_x, c_min, c_max)

    return adv_x


def fast_gradient_sign_method_restricted(sess, model, X, Y, eps, modified_percentage, clip_min=None,
                                         clip_max=None, batch_size=256, dataset='nsl-kdd'):
    """
    TODO
    :param sess:
    :param model:
    :param X:
    :param Y:
    :param eps:
    :param clip_min:
    :param clip_max:
    :param batch_size:
    :return:
    """
    # Define TF placeholders for the input and output
    x = tf.placeholder(tf.float32, shape=(None,) + X.shape[1:])
    y = tf.placeholder(tf.float32, shape=(None,) + Y.shape[1:])
    if 'nsl-kdd' in dataset:
        adv_x = fgsm(
            x, model(x), eps=eps, modified_percentage=modified_percentage,
            clip_min=clip_min,
            clip_max=clip_max, y=y
        )
    elif 'cicids' in dataset:
        adv_x = fgsm_cicids(x, model(x), eps=eps, modified_percentage=modified_percentage,
                            clip_min=clip_min,
                            clip_max=clip_max, y=y)
    X_adv, = batch_eval(
        sess, [x, y], [adv_x],
        [X, Y], args={'batch_size': batch_size}
    )

    return X_adv


def basic_iterative_method_restricted(sess, model, X, Y, eps, modified_percentage, eps_iter, nb_iter=50, clip_min=None,
                                      clip_max=None, batch_size=256, dataset='nsl-kdd'):
    """
    TODO
    :param sess:
    :param model:
    :param X:
    :param Y:
    :param eps:
    :param eps_iter:
    :param nb_iter:
    :param clip_min:
    :param clip_max:
    :param batch_size:
    :return:
    """
    # Define TF placeholders for the input and output
    x = tf.placeholder(tf.float32, shape=(None,)+X.shape[1:])
    y = tf.placeholder(tf.float32, shape=(None,)+Y.shape[1:])
    # results will hold the adversarial inputs at each iteration of BIM;
    # thus it will have shape (nb_iter, n_samples, n_rows, n_cols, n_channels)
    results = np.zeros((nb_iter, X.shape[0],) + X.shape[1:])
    # Initialize adversarial samples as the original samples, set upper and
    # lower bounds
    X_adv = X
    # X_min = X_adv - eps
    # X_max = X_adv + eps

    lower_bound = X - (clip_max - clip_min) * 0.001
    upper_bound = X + (clip_max - clip_min) * modified_percentage
    # lower_bound = X_adv - eps
    # upper_bound = X_adv + eps
    X_min = np.maximum(clip_min, lower_bound)
    X_max = np.minimum(clip_max, upper_bound)
    print('Running BIM iterations...')
    # "its" is a dictionary that keeps track of the iteration at which each
    # sample becomes misclassified. The default value will be (nb_iter-1), the
    # very last iteration.
    def f(val):
        return lambda: val
    its = defaultdict(f(nb_iter-1))
    # Out keeps track of which samples have already been misclassified
    out = set()
    for i in tqdm(range(nb_iter)):
        if 'nsl-kdd' in dataset:
            adv_x = fgsm(
                x, model(x), eps=eps_iter, modified_percentage=modified_percentage,
                clip_min=clip_min, clip_max=clip_max, y=y)
        elif 'cicids' in dataset:
            adv_x = fgsm_cicids(x, model(x), eps=eps, modified_percentage=modified_percentage,
                                clip_min=clip_min,
                                clip_max=clip_max, y=y)

        X_adv, = batch_eval(
            sess, [x, y], [adv_x],
            [X_adv, Y], args={'batch_size': batch_size}
        )
        X_adv = np.maximum(np.minimum(X_adv, X_max), X_min)
        results[i] = X_adv
        # check misclassifieds
        #predictions = model.predict_classes(X_adv, batch_size=512, verbose=0)
        predictions = model.predict(X_adv, batch_size=512, verbose=0)
        predictions = np.argmax(predictions, axis=1)
        misclassifieds = np.where(predictions != Y.argmax(axis=1))[0]
        for elt in misclassifieds:
            if elt not in out:
                its[elt] = i
                out.add(elt)

    return its, results

def saliency_map_method(sess, model, X, Y, theta, gamma, clip_min=None,
                        clip_max=None):
    """

    :param sess:
    :param model:
    :param X:
    :param Y:
    :param theta:
    :param gamma:
    :param clip_min:
    :param clip_max:
    :return:
    """
    nb_classes = Y.shape[1]
    X_adv = np.zeros_like(X)
    # Instantiate a SaliencyMapMethod attack object
    jsma = SaliencyMapMethod(model, back='tf', sess=sess)
    jsma_params = {'theta': theta, 'gamma': gamma,
                   'clip_min': clip_min, 'clip_max': clip_max,
                   'y_target': None}
    for i in tqdm(range(len(X))):
        # Get the sample
        sample = X[i:(i+1)]
        # First, record the current class of the sample
        current_class = int(np.argmax(Y[i]))
        # Randomly choose a target class
        target_class = np.random.choice(other_classes(nb_classes,
                                                      current_class))
        # This call runs the Jacobian-based saliency map approach
        one_hot_target = np.zeros((1, nb_classes), dtype=np.float32)
        one_hot_target[0, target_class] = 1
        jsma_params['y_target'] = one_hot_target
        X_adv[i] = jsma.generate_np(sample, **jsma_params)

    return X_adv