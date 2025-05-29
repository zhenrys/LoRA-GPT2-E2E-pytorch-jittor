#  ------------------------------------------------------------------------------------------
#  Copyright (c) Microsoft Corporation. All rights reserved.
#  Licensed under the MIT License (MIT). See LICENSE in the repo root for license information.
#  ------------------------------------------------------------------------------------------
import argparse
import time
import math
import os, sys
import numpy as np
import itertools
import json

# 使用jittor替代torch
import jittor as jt
import jittor.nn as nn
import random

from log import Logger


from optimizer import (
    create_optimizer_scheduler,
    add_optimizer_params,
    create_adam_optimizer_from_args
)

from data_utils import FT_Dataset
from model import GPT2Config, GPT2LMModel

import loralib as lora

train_loss_list=list()

parser = argparse.ArgumentParser(description='PyTorch GPT2 ft script')
parser.add_argument('--random_seed', default=2025, type=int,help='random seed')
add_optimizer_params(parser)
parser.add_argument('--train_data', required=True, help='location of training data corpus')

parser.add_argument('--valid_data', required=True, help='location of validation data corpus')

parser.add_argument('--train_batch_size', type=int, default=8, help='training batch size')

parser.add_argument('--valid_batch_size', type=int, default=4, help='validation batch size')

parser.add_argument('--grad_acc', type=int, default=1, help='gradient accumulation steps')

parser.add_argument('--clip', type=float, default=0.0, help='gradient clip')

parser.add_argument('--seq_len', type=int, default=512, help='number of tokens to predict.')

parser.add_argument('--model_card', default='gpt2.md', choices=['gpt2.sm', 'gpt2.md', 'gpt2.lg'], 
                    help='model names')

parser.add_argument('--init_checkpoint', default=None, help='pretrained checkpoint path')

parser.add_argument('--fp16', action='store_true', help='train model with fp16')

parser.add_argument('--log_interval', type=int, default=100, help='log interval')

parser.add_argument('--eval_interval', type=int, default=2000, help='eval interval')

parser.add_argument('--save_interval', type=int, default=500, help='save interval')

parser.add_argument('--work_dir', type=str, default=os.getenv('PT_OUTPUT_DIR', 'gpt2_model'), 
                    help='working folder.')

parser.add_argument('--lora_dim', type=int, default=0, help='lora attn dimension')

parser.add_argument('--lora_alpha', type=int, default=128, help='lora attn alpha')

parser.add_argument('--obj', default='clm', choices=['jlm', 'clm'], 
                    help='language model training objective')

parser.add_argument('--lora_dropout', default=0.0, type=float, 
                    help='dropout probability for lora layers')

parser.add_argument('--label_smooth', default=0.0, type=float, help='label smoothing')

parser.add_argument('--roll_interval', type=int, default=-1, help='rolling interval')

parser.add_argument('--roll_lr', type=float, default=0.00001, help='rolling learning rate')

parser.add_argument('--roll_step', type=int, default=100, help='rolling step')

parser.add_argument('--eval_epoch', type=int, default=1, help='eval per number of epochs')

def parse_gpu(args):

    jt.set_global_seed(args.random_seed)  # 设定随机种子，确保可复现
    jt.flags.use_cuda = 1
    args.device = "cuda"

# influence model, calculate the influence score between two samples.
def print_args(args):
    logger.log('=' * 100)
    for k, v in args.__dict__.items():
        logger.log(f'        - {k} : {v}')
    logger.log('=' * 100)


class AverageMeter(object):
    """Computes and stores the average and current value
         Imported from https://github.com/pytorch/examples/blob/master/imagenet/main.py#L247-L262
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count


def optimizer_step(_loss, _optimizer, _model, _schedule, args, is_update=True):
    optimizer.backward(_loss)

    if is_update:
        if args.clip > 0:
            _optimizer.clip_grad_norm(_model.parameters(), args.clip)

        _optimizer.step()
        _optimizer.zero_grad()

    if _schedule is not None:
        _schedule.step()


def evaluate(model, valid_loader, args):
    model.eval()
    total_loss = 0.
    start_time = time.time()

    avg_lm_loss = AverageMeter()

    with jt.no_grad():
        for idx, data in enumerate(valid_loader):
            data = {key: value for key, value in data.items()}

            _input = data['input'].to(args.device)
            _target = data['target'].to(args.device)
            _msk = data['mask'].to(args.device)

            _lm_logits, _loss = model(_input, lm_labels=_target, lm_mask=_msk) 
            loss = _loss.mean() 
            
            avg_lm_loss.update(loss.item())

            if idx % 100 == 0:
                logger.log(f'eval samples: {idx}, loss: {loss.float()}')

        total_time = time.time() - start_time
        logger.log(f'average loss: +{avg_lm_loss.avg}')
    return avg_lm_loss.avg, math.exp(avg_lm_loss.avg)

Ave_time_lm=AverageMeter()
def train_validate(
    model, 
    optimizer, 
    scheduler, 
    train_loader, 
    valid_loader, 
    args, 
    train_step=0, 
    epoch=0
):
    model.train()
    avg_lm_loss = AverageMeter()
    logger.log(f'start to train the model................ {epoch}')
    log_start_time = time.time()
    best_val_ppl = None
    avg_time = AverageMeter()
    jt.sync_all(True)
    for idx, data in enumerate(train_loader):
        # print("here",'='*100)
        data = {key: value for key, value in data.items()}
        # print(data['input'].device,args.device,'='*100)
        _input = data['input'].to(args.device)
        # print(_input, '高手是你？')
        # _input = data['input'].cuda()

        _target = data['target'].to(args.device)
        _msk = data['mask'].to(args.device)
        # print(_input.shape,'阿？')

        _lm_logits, _lm_loss = model(
            _input, lm_labels=_target, lm_mask=_msk, label_smooth=args.label_smooth
        )
        # print(_lm_loss, '我请问你是谁呢？')
        _lm_loss = _lm_loss.mean() 

        train_step += 1
        is_update = True if train_step % args.grad_acc == 0 else False

        avg_lm_loss.update(_lm_loss.item())
        # print(avg_lm_loss.val, '=' * 100)
        optimizer_step(
            _lm_loss/(args.grad_acc), optimizer, model, scheduler, args, is_update=is_update
        )
        # print(train_step,epoch,args.log_interval)
        if train_step % args.log_interval == 0:
            jt.sync_all(True)
            elapsed = time.time() - log_start_time
            avg_time.update(elapsed * 1000 / args.log_interval)

            lr = optimizer.param_groups[0]['lr']
            log_str = f'| epoch {epoch:3d} step {train_step:>8d} | { idx + 1:>6d} batches | ' \
                      f'lr {lr:.3g} | ms/batch {elapsed * 1000 / args.log_interval:5.2f} | ' \
                      f'loss {avg_lm_loss.val:5.2f} | avg loss {avg_lm_loss.avg:5.2f} | ' \
                      f'ppl {math.exp(avg_lm_loss.avg):5.2f}'
            train_loss_list.append(avg_lm_loss.avg)
            logger.log(log_str)
            jt.sync_all(True)
            log_start_time = time.time()
            avg_lm_loss.reset()
        
        if train_step % args.save_interval == 0:
            model_path = os.path.join(args.work_dir, f'model.{train_step}.ckpt')
            logger.log(f'saving checkpoint, {model_path}')
            jt.save({'model_state_dict': lora.lora_state_dict(model)}, model_path)
            # distributed_sync(args)

        # evaluation interval
        if train_step % args.eval_interval == 0:
            eval_start_time = time.time()

            valid_loss, valid_ppl = evaluate(model, valid_loader, args)

            if best_val_ppl is None or valid_ppl < best_val_ppl:
                best_val_ppl = valid_ppl
                
            log_str = f'| Eval {train_step // args.eval_interval:3d} at step {train_step:>8d} | ' \
                      f'time: {time.time() - eval_start_time:5.2f}s | valid loss {valid_loss:5.2f} | ' \
                      f'valid ppl {valid_ppl:5.2f} | best ppl {best_val_ppl:5.2f} '

            logger.log('-' * 100)
            logger.log(log_str)
            logger.log('-' * 100)

            model.train()
            # distributed_sync(args)

        if train_step == args.max_step:
            break

    Ave_time_lm.update(avg_time.avg)
    os.makedirs(args.work_dir, exist_ok=True)
    model_path = os.path.join(args.work_dir, f'model.{train_step}.pkl')
    logger.log(f'saving checkpoint, {model_path}')
    # print(model_path)
    jt.save({'model_state_dict': model.state_dict()}, model_path)
    # distributed_sync(args)
    return train_step

logger = Logger()
if __name__ == '__main__':
    args = parser.parse_args()
    logger.register(f"train_{os.path.normpath(args.train_data).split(os.sep)[-2]}")

    parse_gpu(args)

    print_args(args)
    logger.log('-' * 50 + 'train' + '-' * 50)

    jt.set_global_seed(args.random_seed) 
    random.seed(args.random_seed)

    #data loader
    train_data = FT_Dataset(
        args.train_data, args.train_batch_size, args.seq_len
    ).set_attrs(batch_size=args.train_batch_size)
    
    valid_data = FT_Dataset(
        args.valid_data, args.valid_batch_size, args.seq_len,
    ).set_attrs(batch_size=args.train_batch_size)

    train_loader = jt.dataset.DataLoader(
        train_data, batch_size=args.train_batch_size, num_workers=0, 
        shuffle=True, drop_last=True,
    ).set_attrs(batch_size=args.train_batch_size)
    
    valid_loader = jt.dataset.DataLoader(
        valid_data, batch_size=args.valid_batch_size, num_workers=0, 
        shuffle=True, drop_last=False,
    ).set_attrs(batch_size=args.train_batch_size)

    if args.model_card == 'gpt2.sm':
        config = GPT2Config(
            n_embd=768, n_layer=12, n_head=12, 
            lora_attn_dim=args.lora_dim, 
            lora_attn_alpha=args.lora_alpha, 
            lora_dropout=args.lora_dropout,
        )
    elif args.model_card == 'gpt2.md':
        config = GPT2Config(
            n_embd=1024, n_layer=24, n_head=16, 
            lora_attn_dim=args.lora_dim, 
            lora_attn_alpha=args.lora_alpha, 
            lora_dropout=args.lora_dropout,
        )
    elif args.model_card == 'gpt2.lg':
        config = GPT2Config(
            n_embd=1280, n_layer=36, n_head=20, 
            lora_attn_dim=args.lora_dim, 
            lora_attn_alpha=args.lora_alpha, 
            lora_dropout=args.lora_dropout,
        )
    lm_net = GPT2LMModel(config)

    if args.init_checkpoint is not None:
        logger.log('loading model pretrained weight.')
        weights=jt.load(args.init_checkpoint)
        lm_net.load_weight(weights)

    lm_net = lm_net.cuda()

    # use lora 
    if args.lora_dim > 0:
        lora.mark_only_lora_as_trainable(lm_net)

    optimizer = create_adam_optimizer_from_args(lm_net, args)
    
    # set optimizer parameter
    if args.max_step is None:
        args.max_step = (args.max_epoch * train_data.num_batches)
        logger.log(f'set max_step: {args.max_step}')
    scheduler = create_optimizer_scheduler(optimizer, args)
    
    # finetuing
    try:
        train_step = 0
        for epoch in range(1,args.max_epoch+1):
            train_step = train_validate(
                lm_net, optimizer, scheduler, train_loader, valid_loader, args, 
                train_step=train_step, epoch=epoch
            )
            if train_step >= args.max_step or (args.max_epoch is not None and epoch >= args.max_epoch):
                logger.log('-' * 100)
                logger.log('End of training')
                logger.log(f'ms/batch {Ave_time_lm.avg:5.2f}')
                break
    except KeyboardInterrupt:
            logger.log('-' * 100)
            logger.log('Exiting from training early')


