import math
from typing import  List
import jittor as jt
import jittor.nn as nn
def _calculate_fan_in_and_fan_out(w):
    dimensions = w.dim()
    if dimensions < 2:
        raise ValueError("Fan in and fan out can not be computed for tensor with fewer than 2 dimensions")

    num_input_fmaps = w.size(1)
    num_output_fmaps = w.size(0)
    receptive_field_size = 1
    if w.dim() > 2:
        # math.prod is not always available, accumulate the product manually
        # we could use functools.reduce but that is not supported by TorchScript
        for s in w.shape[2:]:
            receptive_field_size *= s
    fan_in = num_input_fmaps * receptive_field_size
    fan_out = num_output_fmaps * receptive_field_size

    return fan_in, fan_out

class LoRALayer():
    def __init__(
            self,
            r: int,
            lora_alpha: int,
            lora_dropout: float,
            merge_weights: bool,
    ):
        self.r = r
        self.lora_alpha = lora_alpha
        # Optional dropout
        if lora_dropout > 0.:
            self.lora_dropout = nn.Dropout(p=lora_dropout)
        else:
            self.lora_dropout = lambda x: x
        # Mark the weight as unmerged
        self.merged = False
        self.merge_weights = merge_weights


class Embedding(nn.Embedding, LoRALayer):
    # LoRA_GPT2 implemented in a dense layer
    def __init__(
            self,
            num_embeddings: int,
            embedding_dim: int,
            r: int = 0,
            lora_alpha: int = 1,
            merge_weights: bool = True,
            **kwargs
    ):
        nn.Embedding.__init__(self, num_embeddings, embedding_dim, **kwargs)
        LoRALayer.__init__(self, r=r, lora_alpha=lora_alpha, lora_dropout=0,
                           merge_weights=merge_weights)
        # Actual trainable parameters
        if r > 0:
            self.lora_A = self.weight.new_zeros((r, num_embeddings))
            self.lora_B = self.weight.new_zeros((embedding_dim, r))
            self.scaling = self.lora_alpha / self.r
            # Freezing the pre-trained weight matrix
            self.weight.stop_grad()
        self.reset_parameters()

    def reset_parameters(self):
        nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
        if self.bias is not None:
            fan_in, _ = _calculate_fan_in_and_fan_out(self.weight)
            bound = 1 / math.sqrt(fan_in) if fan_in > 0 else 0
            nn.init.uniform_(self.bias, -bound, bound)
        if hasattr(self, 'lora_A'):
            # initialize A the same way as the default for nn.Linear and B to zero
            nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
            nn.init.zero_(self.lora_B)

    def train(self, mode: bool = True):
        nn.Embedding.train(self)
        if mode:
            if self.merge_weights and self.merged:
                # Make sure that the weights are not merged
                if self.r > 0:
                    self.weight -= (self.lora_B @ self.lora_A).transpose(0, 1) * self.scaling
                self.merged = False
        else:
            if self.merge_weights and not self.merged:
                # Merge the weights and mark it
                if self.r > 0:
                    self.weight += (self.lora_B @ self.lora_A).transpose(0, 1) * self.scaling
                self.merged = True

    def execute(self, x: jt.Var):
        if self.r > 0 and not self.merged:
            result = nn.Embedding.execute(self, x)
            #后面的一些参数？
            after_A = nn.embedding(
                x, self.lora_A.transpose(0, 1)
            )
            result += (after_A @ self.lora_B.transpose(0, 1)) * self.scaling
            return result
        else:
            return nn.Embedding.execute(self, x)


class Linear(nn.Linear, LoRALayer):
    # LoRA_GPT2 implemented in a dense layer
    def __init__(
            self,
            in_features: int,
            out_features: int,
            r: int = 0,
            lora_alpha: int = 1,
            lora_dropout: float = 0.,
            fan_in_fan_out: bool = False,
            # Set this to True if the layer to replace stores weight like (fan_in, fan_out)
            merge_weights: bool = True,
            **kwargs
    ):
        nn.Linear.__init__(self, in_features, out_features, **kwargs)
        LoRALayer.__init__(self, r=r, lora_alpha=lora_alpha, lora_dropout=lora_dropout,
                           merge_weights=merge_weights)

        self.fan_in_fan_out = fan_in_fan_out
        # Actual trainable parameters
        if r > 0:
            self.lora_A = self.weight.new_zeros((r, in_features))
            self.lora_B = self.weight.new_zeros((out_features, r))
            self.scaling = self.lora_alpha / self.r
            # Freezing the pre-trained weight matrix
            self.weight.stop_grad()
        self.reset_parameters()
        if fan_in_fan_out:
            self.weight = self.weight.transpose(0, 1)

    def reset_parameters(self):
        nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
        if self.bias is not None:
            fan_in, _ = _calculate_fan_in_and_fan_out(self.weight)
            bound = 1 / math.sqrt(fan_in) if fan_in > 0 else 0
            nn.init.uniform_(self.bias, -bound, bound)
        if hasattr(self, 'lora_A'):
            # initialize A the same way as the default for nn.Linear and B to zero
            nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
            nn.init.zero_(self.lora_B)

    def train(self, mode: bool = True):
        def T(w):
            return w.transpose(0, 1) if self.fan_in_fan_out else w

        nn.Linear.train(self)
        if mode:
            if self.merge_weights and self.merged:
                # Make sure that the weights are not merged
                if self.r > 0:
                    self.weight -= T(self.lora_B @ self.lora_A) * self.scaling
                self.merged = False
        else:
            if self.merge_weights and not self.merged:
                # Merge the weights and mark it
                if self.r > 0:
                    self.weight += T(self.lora_B @ self.lora_A) * self.scaling
                self.merged = True

    def execute(self, x: jt.Var):
        def T(w):
            return w.transpose(0, 1) if self.fan_in_fan_out else w

        if self.r > 0 and not self.merged:
            result = nn.linear(x, T(self.weight), bias=self.bias)
            result += (self.lora_dropout(x) @ self.lora_A.transpose(0, 1) @ self.lora_B.transpose(0, 1)) * self.scaling
            return result
        else:
            return nn.linear(x, T(self.weight), bias=self.bias)


class MergedLinear(nn.Linear, LoRALayer):
    # LoRA_GPT2 implemented in a dense layer
    def __init__(
            self,
            in_features: int,
            out_features: int,
            r: int = 0,
            lora_alpha: int = 1,
            lora_dropout: float = 0.,
            enable_lora: jt.Var = jt.array([False]),
            fan_in_fan_out: bool = False,
            merge_weights: bool = True,
            **kwargs
    ):
        nn.Linear.__init__(self, in_features, out_features, **kwargs)
        LoRALayer.__init__(self, r=r, lora_alpha=lora_alpha, lora_dropout=lora_dropout,
                           merge_weights=merge_weights)
        assert out_features % enable_lora.shape[0] == 0, \
            'The length of enable_lora must divide out_features'
        self.enable_lora = enable_lora
        self.enable_lora.stop_grad()
        self.fan_in_fan_out = fan_in_fan_out
        # Actual trainable parameters
        if r > 0 and self.enable_lora.sum().item()>0:
            self.lora_A=self.weight.new_zeros((r * enable_lora.sum().item(), in_features))
            # print(self.lora_A.shape, 'lllllla' * 50,enable_lora.sum().item())

            self.lora_B=self.weight.new_zeros((out_features // enable_lora.shape[0] * enable_lora.sum().item(), r)
            )  # weights for Conv1D with groups=sum(enable_lora)
            # print(self.lora_B.shape, enable_lora.sum().item(),'llllllb' * 50)

            self.scaling = self.lora_alpha / self.r
            # Freezing the pre-trained weight matrix
            self.weight.stop_grad()
            # Compute the indices
            self.lora_ind = self.weight.new_zeros(
                (out_features,)
            ).view(enable_lora.shape[0], -1)
            # print(jt.where(enable_lora)[0],'dsdfsdf*100')
            self.lora_ind[jt.where(enable_lora)[0] , :] = True ###索引赋值
            # print(out_features,self.lora_ind.shape,enable_lora.shape[0],enable_lora.sum().item(),'mamama'*100)
            self.lora_ind = self.lora_ind.view(-1)
            # print(self.lora_ind.sum().item())
            # print(self.lora_ind.sum().item(), self.lora_ind.shape)
            self.lora_ind.stop_grad()
        self.reset_parameters()
        # print(self.weight.shape, 'aaaa' * 100, fan_in_fan_out)
        if fan_in_fan_out:
            # print('YES')
            self.weight = self.weight.transpose(0,1) ##关键
            # print(self.weight.shape, 'aaaa' * 100, fan_in_fan_out)


    def reset_parameters(self):
        nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
        if self.bias is not None:
            fan_in, _ = _calculate_fan_in_and_fan_out(self.weight)
            bound = 1 / math.sqrt(fan_in) if fan_in > 0 else 0
            nn.init.uniform_(self.bias, -bound, bound)
        if hasattr(self, 'lora_A'):
            # initialize A the same way as the default for nn.Linear and B to zero
            nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
            nn.init.zero_(self.lora_B)

    def zero_pad(self, x):
        result = x.new_zeros((self.lora_ind.shape[0], *x.shape[1:]))
        # print(len(self.lora_ind), *x.shape[1:], result.shape,self.lora_ind.shape, x.shape,'敢用len？')
        # print(self.lora_ind.sum().item(),x.shape)
        result[jt.where(self.lora_ind)[0],:] = x #坑！！！
        return result

    def merge_AB(self):
        def T(w):
            return w.transpose(0, 1) if self.fan_in_fan_out else w
        con1d=nn.Conv1d(
            in_channels=self.lora_A.unsqueeze(0).shape[1],
            out_channels=self.lora_B.unsqueeze(-1).shape[0],
            kernel_size=self.lora_B.unsqueeze(-1).shape[2],
            groups=self.enable_lora.sum().item(),
            bias=False #调了我一万年！！！！！
        )


        con1d.weight=self.lora_B.unsqueeze(-1)
        # print(con1d(self.lora_A.unsqueeze(0)).shape)
        delta_w=con1d(self.lora_A.unsqueeze(0)).squeeze(0)
        # print('不信:', delta_w)
        # print('谁能挡我：', delta_w)
        return T(self.zero_pad(delta_w))

    def train(self, mode: bool = True):
        def T(w):
            return w.transpose(0, 1) if self.fan_in_fan_out else w

        nn.Linear.train(self)
        if mode:
            if self.merge_weights and self.merged:
                # Make sure that the weights are not merged
                if self.r > 0 and self.enable_lora.sum().item()>0:
                    self.weight -= self.merge_AB() * self.scaling
                self.merged = False
        else:
            if self.merge_weights and not self.merged:
                # Merge the weights and mark it
                if self.r > 0 and self.enable_lora.sum().item()>0:
                    self.weight += self.merge_AB() * self.scaling
                self.merged = True

    def execute(self, x: jt.Var):
        def T(w):
            return w.transpose(0, 1) if self.fan_in_fan_out else w

        if self.merged:
            return nn.linear(x, T(self.weight), bias=self.bias)
        else:
            result = nn.linear(x, T(self.weight), bias=self.bias)
            if self.r > 0:
                result += self.lora_dropout(x) @ T(self.merge_AB().transpose(0,1)) * self.scaling
            return result


class ConvLoRA(nn.Module, LoRALayer):
    def __init__(self, conv_module, in_channels, out_channels, kernel_size, r=0, lora_alpha=1, lora_dropout=0.,
                 merge_weights=True, **kwargs):
        super(ConvLoRA, self).__init__()
        self.conv = conv_module(in_channels, out_channels, kernel_size, **kwargs)
        for name, param in self.conv.named_parameters():
            self.register_parameter(name, param)
        LoRALayer.__init__(self, r=r, lora_alpha=lora_alpha, lora_dropout=lora_dropout, merge_weights=merge_weights)
        assert isinstance(kernel_size, int)
        # Actual trainable parameters
        if r > 0:
            self.lora_A = nn.Parameter(
                self.conv.weight.new_zeros((r * kernel_size, in_channels * kernel_size))
            )
            self.lora_B = nn.Parameter(
                self.conv.weight.new_zeros((out_channels // self.conv.groups * kernel_size, r * kernel_size))
            )
            self.scaling = self.lora_alpha / self.r
            # Freezing the pre-trained weight matrix
            self.conv.weight.requires_grad = False
        self.reset_parameters()
        self.merged = False

    def reset_parameters(self):
        nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
        if self.bias is not None:
            fan_in, _ = _calculate_fan_in_and_fan_out(self.weight)
            bound = 1 / math.sqrt(fan_in) if fan_in > 0 else 0
            nn.init.uniform_(self.bias, -bound, bound)
        if hasattr(self, 'lora_A'):
            # initialize A the same way as the default for nn.Linear and B to zero
            nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
            nn.init.zero_(self.lora_B)

    def train(self, mode=True):
        super(ConvLoRA, self).train()
        if mode:
            if self.merge_weights and self.merged:
                if self.r > 0:
                    # Make sure that the weights are not merged
                    self.conv.weight -= (self.lora_B @ self.lora_A).view(self.conv.weight.shape) * self.scaling
                self.merged = False
        else:
            if self.merge_weights and not self.merged:
                if self.r > 0:
                    # Merge the weights and mark it
                    self.conv.weight += (self.lora_B @ self.lora_A).view(self.conv.weight.shape) * self.scaling
                self.merged = True

    def execute(self, x):
        if self.r > 0 and not self.merged:
            return self.conv._conv_forward(
                x,
                self.conv.weight + (self.lora_B @ self.lora_A).view(self.conv.weight.shape) * self.scaling,
                self.conv.bias
            )
        return self.conv(x)


class Conv2d(ConvLoRA):
    def __init__(self, *args, **kwargs):
        super(Conv2d, self).__init__(nn.Conv2d, *args, **kwargs)


class Conv1d(ConvLoRA):
    def __init__(self, *args, **kwargs):
        super(Conv1d, self).__init__(nn.Conv1d, *args, **kwargs)


# Can Extend to other ones like this

class Conv3d(ConvLoRA):
    def __init__(self, *args, **kwargs):
        super(Conv3d, self).__init__(nn.Conv3d, *args, **kwargs)
