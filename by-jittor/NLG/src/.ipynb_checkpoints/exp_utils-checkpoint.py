#  ------------------------------------------------------------------------------------------
#  Copyright (c) Microsoft Corporation. All rights reserved.
#  Licensed under the MIT License (MIT). See LICENSE in the repo root for license information.
#  ------------------------------------------------------------------------------------------
import os

# 使用jittor替代torch
import jittor as jt

def save_checkpoint(model, optimizer, path, epoch):
    jt.save(model, os.path.join(path, 'model_{}.pt'.format(epoch)))
    jt.save(optimizer.state_dict(), os.path.join(path, 'optimizer_{}.pt'.format(epoch)))
