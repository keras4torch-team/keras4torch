import torch
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
import pandas as pd
import torchsummary
from collections import OrderedDict
from torch.utils.data import random_split

from ._training import Trainer
from .metrics import Metric
from .metrics import create_metric_by_name
from .losses import create_loss_by_name
from .optimizers import create_optimizer_by_name

__version__ = '0.3.0'

class Model(torch.nn.Module):
    """
    `Model` wraps a `nn.Module` with training and inference features.

    Once the model is created, you can config the model with losses and metrics\n  with `model.compile()`, train the model with `model.fit()`, or use the model\n  to do prediction with `model.predict()`.
    """
    def __init__(self, model):
        super(Model, self).__init__()
        self.model = model
        self.compiled = False

    def forward(self, x):
        return self.model.forward(x)

    @staticmethod
    def to_tensor(*args):
        rt = []
        for arg in args:
            if isinstance(arg, pd.DataFrame):
                arg = torch.from_numpy(arg.values)
            elif isinstance(arg, np.ndarray):
                arg = torch.from_numpy(arg)
            elif not isinstance(arg, torch.Tensor):
                raise TypeError('Only DataFrame, ndarray and torch.Tensor are supported.')
            rt.append(arg)
                
        return rt[0] if len(rt) == 1 else tuple(rt)

    def count_params(self) -> int:
        """Count the total number of scalars composing the weights."""
        return sum([p.numel() for p in self.parameters()])

    ########## keras-style methods below ##########

    def summary(self, input_shape, depth=3):
        """Prints a string summary of the network."""
        torchsummary.summary(self.model, input_shape, depth=depth, verbose=1)

    def compile(self, optimizer, loss, device=None, metrics=None):
        """
        Configures the model for training.

        Args:

        * :attr:`optimizer`: String (name of optimizer) or optimizer instance.

        * :attr:`loss`: String (name of objective function), objective function or loss instance.

        * :attr:`metrics`: List of metrics to be evaluated by the model during training. You can also use dict to specify the 
        abbreviation of each metric.

        * :attr:`device`: Device the model will run on, if `None` it will use 'cuda' when `torch.cuda.is_available()` otherwise 'cpu'.
        """
        self.compiled = True
        if isinstance(loss, str):
            loss = create_loss_by_name(loss)
        if isinstance(optimizer, str):
            optimizer = create_optimizer_by_name(optimizer, self.parameters())

        m = OrderedDict({'loss': loss})
        if isinstance(metrics, dict):
            m.update(metrics)
        elif isinstance(metrics, list):
            for tmp_m in metrics:
                if isinstance(tmp_m, str):
                    tmp_m = create_metric_by_name(tmp_m)
                if isinstance(tmp_m, Metric):
                    m[tmp_m.get_abbr()] = tmp_m
                elif hasattr(tmp_m, '__call__'):
                    m[tmp_m.__name__] = tmp_m
                else:
                    raise TypeError('Unsupported type.')
        else:
            raise TypeError('Argument `metrics` should be either a dict or list.')

        if device == None:
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.to(device=device)
        self.trainer = Trainer(model=self, optimizer=optimizer, loss=loss, metrics=m, device=device)


    def fit(self, x, y, epochs, batch_size=32,
                validation_split=None, val_split_seed=None,
                validation_data=None,
                callbacks=[],
                verbose=1,
                precise_mode=False,
                ):
        """Trains the model for a fixed number of epochs (iterations on a dataset)."""

        assert self.compiled
        x, y = self.to_tensor(x, y)

        assert not (validation_data != None and validation_split != None)
        has_val = validation_data != None or validation_split != None

        train_set = TensorDataset(x, y)
    
        if validation_data != None:
            x_val, y_val = self.to_tensor(validation_data[0], validation_data[1])
            val_set = TensorDataset(x_val, y_val)

        if validation_split != None:
            val_length = int(len(train_set) * validation_split)
            train_length = len(train_set) - val_length
            if val_split_seed != None:
                train_set, val_set = random_split(train_set, [train_length, val_length], generator=torch.Generator().manual_seed(val_split_seed))
            else:
                train_set, val_set = random_split(train_set, [train_length, val_length])

        train_loader = DataLoader(train_set, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_set, batch_size=batch_size, shuffle=False) if has_val else None

        # Training
        self.trainer.register_callbacks(callbacks)
        history = self.trainer.run(train_loader, val_loader, max_epochs=epochs, verbose=verbose, precise_mode=precise_mode)

        return history

    @torch.no_grad()
    def evaluate(self, x, y, batch_size=32):
        """Returns the loss value & metrics values for the model in test mode.\n\n    Computation is done in batches."""
        assert self.compiled
        x, y = self.to_tensor(x, y)
        val_loader = DataLoader(TensorDataset(x, y), batch_size=batch_size, shuffle=False)
        return self.trainer.evaluate(val_loader)

    @torch.no_grad()
    def predict(self, inputs, batch_size=32, device=None):
        """Generates output predictions for the input samples.\n\n    Computation is done in batches."""
        if device == None:
            device = 'cuda' if torch.cuda.is_available() else 'cpu'

        inputs = self.to_tensor(inputs)
        outputs = []
        self.eval()

        data_loader = DataLoader(TensorDataset(inputs), batch_size=batch_size, shuffle=False)
        for x_batch in data_loader:
            outputs.append(self.forward(x_batch[0].to(device=device)))

        return torch.cat(outputs, dim=0).cpu().numpy()

    def save_weights(self, filepath):
        """Equals to `torch.save(model.state_dict(), filepath)`."""
        torch.save(self.state_dict(), filepath)

    def load_weights(self, filepath):
        """Equals to `model.load_state_dict(filepath)`."""
        self.load_state_dict(filepath)