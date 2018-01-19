#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2017 Yasunori Kudo

import argparse
import cv2
import numpy as np
import os
import pickle
from progressbar import ProgressBar
import subprocess
import sys
sys.path.append(os.getcwd())

import chainer
import chainer.functions as F
from chainer import serializers
from chainer import Variable

import dataset
import models.net

def color_jet(x):
    if x < 0.25:
        b = 255
        g = x / 0.25 * 255
        r = 0
    elif x >= 0.25 and x < 0.5:
        b = 255 - (x - 0.25) / 0.25 * 255
        g = 255
        r = 0
    elif x >= 0.5 and x < 0.75:
        b = 0
        g = 255
        r = (x - 0.5) / 0.25 * 255
    else:
        b = 0
        g = 255 - (x - 0.75) / 0.25 * 255
        r = 255
    return int(b), int(g), int(r)

def create_img(k, j, i, variable):
    ps = np.array([0,1,2,0,4,5,0,7,8,9,8,11,12,8,14,15])
    qs = np.array([1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16])
    xs = variable.data[j, 0, i, 0::2].copy()
    ys = variable.data[j, 0, i, 1::2].copy()
    xs *= 100
    xs += 100
    ys *= -100
    ys += 150
    img = np.zeros((350, 200, 3), dtype=np.uint8) + 160
    img = cv2.line(img, (100, 0), (100, 350), (255, 255, 255), 1)
    img = cv2.line(img, (0, 150), (200, 150), (255, 255, 255), 1)
    img = cv2.rectangle(img, (0, 0), (200, 350), (255, 255, 255), 3)
    for i, (p, q) in enumerate(zip(ps, qs)):
        c = 1 / (len(ps) - 1) * i
        b, g, r = color_jet(c)
        img = cv2.line(img, (xs[p], ys[p]), (xs[q], ys[q]), (b, g, r), 2)
    for i in range(17):
        c = 1 / 16 * i
        b, g, r = color_jet(c)
        img = cv2.circle(img, (xs[i], ys[i]), 3, (b, g, r), 3)
    return img

if __name__ == '__main__':
    print(subprocess.check_output(['pyenv', 'version']).decode('utf-8').strip())

    parser = argparse.ArgumentParser()
    parser.add_argument('model_path', type=str)
    parser.add_argument('--row', type=int, default=4)
    parser.add_argument('--col', type=str, default=4)
    args = parser.parse_args()

    col, row = args.col, args.row
    model_path = args.model_path
    with open(os.path.join(os.path.dirname(model_path), 'options.pickle'), 'rb') as f:
        options = pickle.load(f)
    l_seq = options.l_seq

    imgs = np.zeros((l_seq, 350 * col, 600 * row, 3), dtype=np.uint8)
    model = models.net.ConvAE(
        l_latent=64, l_seq=l_seq, mode='generator',
        bn=options.bn, activate_func=getattr(F, options.act_func))
    serializers.load_npz(model_path, model)
    train = dataset.PoseDataset('data/h3.6m', length=l_seq, train=False)
    train_iter = chainer.iterators.SerialIterator(train, batch_size=row, shuffle=True, repeat=False)
    with chainer.no_backprop_mode(), chainer.using_config('train', False):
        pbar = ProgressBar(col)
        for k in range(col):
            batch = train_iter.next()
            batch = chainer.dataset.concat_examples(batch)
            xy, z, scale = batch
            xy = Variable(xy)
            z_pred = model(xy)
            theta = np.array([np.pi / 2] * len(xy), dtype=np.float32)
            cos_theta = Variable(np.broadcast_to(np.cos(theta), z_pred.shape[::-1]).transpose(3, 2, 1, 0))
            sin_theta = Variable(np.broadcast_to(np.sin(theta), z_pred.shape[::-1]).transpose(3, 2, 1, 0))
            x = xy[:, :, :, 0::2]
            y = xy[:, :, :, 1::2]

            xx = x * cos_theta + z * sin_theta
            xx = xx[:, :, :, :, None]
            yy = y[:, :, :, :, None]
            real = F.concat((xx, yy), axis=4)
            real = F.reshape(real, (*y.shape[:3], -1))

            xx = x * cos_theta + z_pred * sin_theta
            xx = xx[:, :, :, :, None]
            yy = y[:, :, :, :, None]
            fake = F.concat((xx, yy), axis=4)
            fake = F.reshape(fake, (*y.shape[:3], -1))

            for j in range(row):
                for i in range(l_seq):
                    im0 = create_img(k, j, i, xy)
                    im1 = create_img(k, j, i, real)
                    im2 = create_img(k, j, i, fake)
                    imgs[i, k*350:(k+1)*350, j*600:(j+1)*600] = np.concatenate((im0, im1, im2), axis=1)
            pbar.update(k + 1)

    print('Saving video ...')
    fourcc = cv2.VideoWriter_fourcc(*'H264')
    if not os.path.exists(os.path.join(os.path.dirname(model_path), 'videos')):
        os.mkdir(os.path.join(os.path.dirname(model_path), 'videos'))
    video_path = os.path.join(os.path.dirname(model_path), 'videos',
                              os.path.basename(model_path).replace('.npz', '.mp4'))
    out = cv2.VideoWriter(video_path, fourcc, 20.0, (imgs.shape[2], imgs.shape[1]))
    for img in imgs:
        for k in range(col + 1):
            img = cv2.line(img, (0, k * 350), (row * 600, k * 350), (0, 0, 255), 4)
        for j in range(row + 1):
            img = cv2.line(img, (j * 600, 0), (j * 600, col * 350), (0, 0, 255), 4)
        out.write(img)
    out.release()
    print('Saved video as \'{}\'.'.format(video_path))
