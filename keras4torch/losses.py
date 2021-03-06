from collections import OrderedDict
import torch.nn as nn

_losses_dict = OrderedDict({
    'mse': nn.MSELoss,
    'mae': nn.L1Loss,
    'ce': nn.CrossEntropyLoss,
    'bce': nn.BCEWithLogitsLoss,
    'ce_loss': nn.CrossEntropyLoss,     # deprecated
    'bce_loss': nn.BCEWithLogitsLoss,   # deprecated
})


import torch.nn.functional as F

class CELoss():
    def __init__(self, label_smoothing=0.0, class_weight=None, reduction='mean'):
        self.label_smoothing = label_smoothing
        self.reduction = reduction
        self.class_weight = class_weight
    
    def __call__(self, y_pred, y_true):
        #output = (1.0 - 1e-6) * output + 1e-7
        eps = self.label_smoothing
        c = y_pred.shape[-1]
        target = F.one_hot(y_true, c) * (1 - eps) + eps / c
        log_preds = F.log_softmax(y_pred, dim=-1)

        if self.class_weight is None:
            loss = -(target * log_preds).sum(dim=-1)
        else:
            loss = -(target * log_preds * self.class_weight).sum(dim=-1)

        if self.reduction == 'mean':
            loss = loss.mean()
        return loss


def _create_loss(i):
    if isinstance(i, str):
        name = i.lower()
        if name not in _losses_dict:
            raise KeyError(f'Invalid name, we support {list(_losses_dict.keys())}.')
        return _losses_dict[name]()
    return i

__all__ = ['CELoss']