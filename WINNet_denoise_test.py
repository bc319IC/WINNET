import cv2
import os
import argparse
import glob
import numpy as np
import torch
import torch.nn as nn
from torch.autograd import Variable
from utils.networks import WINNetklvl
from utils.dataset import *

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"

parser = argparse.ArgumentParser(description="WINNet")
parser.add_argument("--num_of_steps", type=int, default=4, help="Number of steps")
parser.add_argument("--num_of_layers", type=int, default=4, help="Number of layers")
parser.add_argument("--num_of_channels", type=int, default=32, help="Number of channels")
parser.add_argument("--lvl", type=int, default=1, help="number of levels")
parser.add_argument("--split", type=str, default="dct", help='splitting operator')
parser.add_argument("--dnlayers", type=int, default=4, help="Number of denoising layers")
parser.add_argument("--logdir", type=str, default="logs", help='path of log files')
parser.add_argument("--test_data", type=str, default='Set12', help='test on Set12 or Set68')
parser.add_argument("--test_noiseL", type=float, default=25, help='noise level used on test set')
parser.add_argument("--train_noiseL", type=float, default=25, help='noise level used on training set')
parser.add_argument("--show_results", type=bool, default=True, help="show results")

opt = parser.parse_args()

def main():
    # Build folders for output images
    if not os.path.exists('results/WINNet'):
        os.makedirs('results/WINNet')
    if not os.path.exists('results/Noisy'):
        os.makedirs('results/Noisy')

    # Build model
    print('Loading model ...\n')
    net = WINNetklvl(steps=opt.num_of_steps, layers=opt.num_of_layers, channels=opt.num_of_channels, klvl=opt.lvl,
                     mode=opt.split, dnlayers=opt.dnlayers)
    device_ids = [0]
    model = nn.DataParallel(net, device_ids=device_ids).cuda()

    print('Load model...')
    model.load_state_dict(torch.load(os.path.join(opt.logdir, 'net_WINNet.pth')))
    #temp = list(model.parameters())
    #print(temp)

    pytorch_total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print('Total Number of Parameters: ', pytorch_total_params)

    torch.manual_seed(1234)# for reproducibility
    model.eval()
    # load data info
    files_source = glob.glob(os.path.join('data', opt.test_data, '*.png'))
    files_source.sort()
    # process data
    psnr_avg = 0
    i = 1
    for f in files_source:
        # image
        Img = cv2.imread(f)
        ImgT = Img
        Img = normalize(np.float32(Img[:,:,0]))
        Img = np.expand_dims(Img, 0)
        Img = np.expand_dims(Img, 1)
        ISource = torch.Tensor(Img)
        # noise
        #noise = torch.FloatTensor(ISource.size()).normal_(mean=0, std=opt.test_noiseL/255.) # AG CG
        noise = np.zeros((ImgT.shape[0],ImgT.shape[1]),dtype=np.uint8) #SP
        cv2.randu(noise,0,255) #SP
        noisew = cv2.threshold(noise,220,255,cv2.THRESH_BINARY)[1]*(-1) #SP
        cv2.randu(noise,0,255) #SP
        noiseb = cv2.threshold(noise,220,255,cv2.THRESH_BINARY)[1] #SP
        noise = noiseb+noisew #SP
        noise = torch.Tensor(noise) #SP
        con_noise = np.concatenate([np.random.normal(0, 15/225, size=(ImgT.shape[0]//2, ImgT.shape[1])),np.random.normal(0, 50/255, size=(ImgT.shape[0]//2, ImgT.shape[1]))]) #CG change +1 accordingly
        np.random.shuffle(con_noise) #CG
        con_noise = torch.FloatTensor(con_noise) #CG
        # noisy image
        INoisy = ISource + noise #AG SP
        #INoisy = torch.poisson(ISource) #P
        #INoisy = ISource + noise + con_noise #CG
        ISource, INoisy = Variable(ISource.cuda()), Variable(INoisy.cuda())

        stdNv_test = Variable(opt.test_noiseL * torch.ones(1).cuda())
        stdNv_train = Variable(opt.train_noiseL * torch.ones(1).cuda())
        with torch.no_grad():
            #INoisy=INoisy[:,:,0:20,0:20] # COEFFICIENTS MAP
            Out, _ = model(INoisy, stdNv_test, stdNv_train)
            #print(torch.max(Out))
            #print(torch.min(Out))
            Out = torch.clamp(Out, 0., 1.)
        psnr = batch_PSNR(Out, ISource, data_range=1., crop=0)

        #print(opt.show_results)

        # save results
        if opt.show_results:
            save_out_path = "results/WINNet/img_{}.png".format(i)
            #print(torch.max(Out))
            #print(torch.min(Out))
            save_img(save_out_path, Out)
            save_out_path = "results/Noisy/nimg_{}.png".format(i)
            save_img(save_out_path, torch.clamp(INoisy, 0., 1.))
        print("%s PSNR %f" % (f, psnr))
        i += 1
        psnr_avg += psnr
    psnr_avg /= len(files_source)
    print("Average PSNR: %f" % (psnr_avg))

if __name__ == "__main__":
    main()
