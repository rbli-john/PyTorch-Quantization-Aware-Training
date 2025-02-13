import os
import random

import torch
import torch.nn as nn
import torch.optim as optim
import torchvision
from torchvision import datasets, transforms

import time
import copy
import numpy as np
import logging
# logging.basicConfig(format='%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s', level=logging.INFO)
logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)

from resnet import resnet18
from vovnet import VovNet

CIFAR10 = 'cifar10'
FASHION_MNIST = 'fashion_nist'


def set_random_seeds(random_seed=0):

    torch.manual_seed(random_seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    np.random.seed(random_seed)
    random.seed(random_seed)


def prepare_dataloader(num_workers=8,
                       train_batch_size=128,
                       eval_batch_size=256,
                       dataset: str=None):
    if dataset == CIFAR10:
        train_transform = transforms.Compose([
            transforms.RandomCrop(32, padding=4),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            # transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
            transforms.Normalize(mean=(0.485, 0.456, 0.406),
                                 std=(0.229, 0.224, 0.225))
        ])

        test_transform = transforms.Compose([
            transforms.ToTensor(),
            # transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
            transforms.Normalize(mean=(0.485, 0.456, 0.406),
                                 std=(0.229, 0.224, 0.225))
        ])

        train_set = torchvision.datasets.CIFAR10(root="data",
                                                 train=True,
                                                 download=True,
                                                 transform=train_transform)
        # We will use test set for validation and test in this project.
        # Do not use test set for validation in practice!
        test_set = torchvision.datasets.CIFAR10(root="data",
                                                train=False,
                                                download=True,
                                                transform=test_transform)
    elif dataset == FASHION_MNIST:
        train_transform = transforms.Compose([
            transforms.Resize((32, 32)),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize((0.5,), (0.5,))
        ])

        test_transform = transforms.Compose([
            transforms.Resize((32, 32)),
            transforms.ToTensor(),
            transforms.Normalize((0.5,), (0.5,))
        ])
        train_set = torchvision.datasets.FashionMNIST(root="data",
                                                      train=True,
                                                      download=True,
                                                      transform=train_transform)
        # We will use test set for validation and test in this project.
        # Do not use test set for validation in practice!
        test_set = torchvision.datasets.FashionMNIST(root="data",
                                                     train=False,
                                                     download=True,
                                                     transform=test_transform)
    else:
        raise NotImplemented()

    train_sampler = torch.utils.data.RandomSampler(train_set)
    test_sampler = torch.utils.data.SequentialSampler(test_set)

    train_loader = torch.utils.data.DataLoader(dataset=train_set,
                                               batch_size=train_batch_size,
                                               sampler=train_sampler,
                                               num_workers=num_workers)

    test_loader = torch.utils.data.DataLoader(dataset=test_set,
                                              batch_size=eval_batch_size,
                                              sampler=test_sampler,
                                              num_workers=num_workers)

    return train_loader, test_loader


def evaluate_model(model, test_loader, device, criterion=None):

    model.eval()
    model.to(device)

    running_loss = 0
    running_corrects = 0

    for inputs, labels in test_loader:

        inputs = inputs.to(device)
        labels = labels.to(device)

        outputs = model(inputs)
        _, preds = torch.max(outputs, 1)

        if criterion is not None:
            loss = criterion(outputs, labels).item()
        else:
            loss = 0

        # statistics
        running_loss += loss * inputs.size(0)
        running_corrects += torch.sum(preds == labels.data)

    eval_loss = running_loss / len(test_loader.dataset)
    eval_accuracy = running_corrects / len(test_loader.dataset)

    return eval_loss, eval_accuracy


def train_model(model,
                train_loader,
                test_loader,
                device,
                learning_rate=1e-1,
                num_epochs=200):

    # The training configurations were not carefully selected.

    criterion = nn.CrossEntropyLoss()

    model.to(device)

    # It seems that SGD optimizer is better than Adam optimizer for ResNet18 training on CIFAR10.
    optimizer = optim.SGD(model.parameters(),
                          lr=learning_rate,
                          momentum=0.9,
                          weight_decay=1e-4)
    # scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=500)
    scheduler = torch.optim.lr_scheduler.MultiStepLR(optimizer,
                                                     milestones=[100, 150],
                                                     gamma=0.1,
                                                     last_epoch=-1)
    # optimizer = optim.Adam(model.parameters(), lr=learning_rate, betas=(0.9, 0.999), eps=1e-08, weight_decay=0, amsgrad=False)

    # Evaluation
    model.eval()
    eval_loss, eval_accuracy = evaluate_model(model=model,
                                              test_loader=test_loader,
                                              device=device,
                                              criterion=criterion)
    logging.info("Epoch: {:03d} Eval Loss: {:.3f} Eval Acc: {:.3f}".format(
        0, eval_loss, eval_accuracy))

    for epoch in range(num_epochs):

        # Training
        model.train()

        running_loss = 0
        running_corrects = 0

        for inputs, labels in train_loader:

            inputs = inputs.to(device)
            labels = labels.to(device)

            # print(f'input.shape: {inputs.size()}')
            # print(f'labels.shape: {labels.size()}')


            # zero the parameter gradients
            optimizer.zero_grad()

            # forward + backward + optimize
            outputs = model(inputs)
            _, preds = torch.max(outputs, 1)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            # statistics
            running_loss += loss.item() * inputs.size(0)
            running_corrects += torch.sum(preds == labels.data)

        train_loss = running_loss / len(train_loader.dataset)
        train_accuracy = running_corrects / len(train_loader.dataset)

        # Evaluation
        model.eval()
        eval_loss, eval_accuracy = evaluate_model(model=model,
                                                  test_loader=test_loader,
                                                  device=device,
                                                  criterion=criterion)

        # Set learning rate scheduler
        scheduler.step()

        logging.info(
            "Epoch: {:03d} Train Loss: {:.3f} Train Acc: {:.3f} Eval Loss: {:.3f} Eval Acc: {:.3f}"
            .format(epoch + 1, train_loss, train_accuracy, eval_loss,
                    eval_accuracy))

    return model


def calibrate_model(model, loader, device=torch.device("cpu:0")):

    model.to(device)
    model.eval()

    for inputs, labels in loader:
        inputs = inputs.to(device)
        labels = labels.to(device)
        _ = model(inputs)


def measure_inference_latency(model,
                              device,
                              input_size=(1, 3, 32, 32),
                              num_samples=100,
                              num_warmups=10):

    model.to(device)
    model.eval()

    x = torch.rand(size=input_size).to(device)

    with torch.no_grad():
        for _ in range(num_warmups):
            _ = model(x)
    torch.cuda.synchronize()

    with torch.no_grad():
        start_time = time.time()
        for _ in range(num_samples):
            _ = model(x)
            torch.cuda.synchronize()
        end_time = time.time()
    elapsed_time = end_time - start_time
    elapsed_time_ave = elapsed_time / num_samples

    return elapsed_time_ave


def save_model(model, model_dir, model_filename):

    if not os.path.exists(model_dir):
        os.makedirs(model_dir)
    model_filepath = os.path.join(model_dir, model_filename)
    torch.save(model.state_dict(), model_filepath)


def load_model(model, model_filepath, device):

    model.load_state_dict(torch.load(model_filepath, map_location=device))

    return model


def save_torchscript_model(model, model_dir, model_filename):

    if not os.path.exists(model_dir):
        os.makedirs(model_dir)
    model_filepath = os.path.join(model_dir, model_filename)
    torch.jit.save(torch.jit.script(model), model_filepath)


def load_torchscript_model(model_filepath, device):

    model = torch.jit.load(model_filepath, map_location=device)

    return model


def create_model(num_classes=10, arch: str='resnet', input_ch=3):
    if arch == 'resnet':
        assert input_ch == 3

        # The number of channels in ResNet18 is divisible by 8.
        # This is required for fast GEMM integer matrix multiplication.
        # model = torchvision.models.resnet18(pretrained=False)
        model = resnet18(num_classes=num_classes, pretrained=False)

        # We would use the pretrained ResNet18 as a feature extractor.
        # for param in model.parameters():
        #     param.requires_grad = False

        # Modify the last FC layer
        # num_features = model.fc.in_features
        # model.fc = nn.Linear(num_features, 10)
    else:
        model = VovNet(num_classes, input_ch=input_ch, vovnet_conv_body='V-19-slim-eSE', norm='BN')

    return model


class QuantizedResNet18(nn.Module):
    def __init__(self, model_fp32):

        super(QuantizedResNet18, self).__init__()
        # QuantStub converts tensors from floating point to quantized.
        # This will only be used for inputs.
        self.quant = torch.quantization.QuantStub()
        # DeQuantStub converts tensors from quantized to floating point.
        # This will only be used for outputs.
        self.dequant = torch.quantization.DeQuantStub()
        # FP32 model
        self.model_fp32 = model_fp32

    def forward(self, x):
        # manually specify where tensors will be converted from floating
        # point to quantized in the quantized model
        x = self.quant(x)
        x = self.model_fp32(x)
        # manually specify where tensors will be converted from quantized
        # to floating point in the quantized model
        x = self.dequant(x)
        return x


def model_equivalence(model_1,
                      model_2,
                      device,
                      rtol=1e-05,
                      atol=1e-08,
                      num_tests=100,
                      input_size=(1, 3, 32, 32)):

    model_1.to(device)
    model_2.to(device)

    for _ in range(num_tests):
        x = torch.rand(size=input_size).to(device)
        y1 = model_1(x).detach().cpu().numpy()
        y2 = model_2(x).detach().cpu().numpy()
        if np.allclose(a=y1, b=y2, rtol=rtol, atol=atol,
                       equal_nan=False) == False:
            print("Model equivalence test sample failed: ")
            print(y1)
            print(y2)
            return False

    return True


def main():
    # finetune = False
    finetune = True
    # finetune_layer_keyword = 'backbone.stem'
    finetune_layer_keyword = 'fc'
    # Maybe need to adjust learning_rate for finetuning?
    # learning_rate = 1e-1  # Learning rate for pre-training
    learning_rate = 1e-2
    num_epochs = 100
    arch = 'vovnet'
    assert arch in ('resnet', 'vovnet')

    dataset_name = FASHION_MNIST
    assert dataset_name in (FASHION_MNIST, CIFAR10)

    print(f'Setting: arch={arch}, lr={learning_rate}, finetune={finetune}, finetune_layer_keyword={finetune_layer_keyword}, num_epochs={num_epochs}, dataset={dataset_name}')

    random_seed = 0
    num_classes = 10
    cuda_device = torch.device("cuda:0")
    cpu_device = torch.device("cpu:0")

    model_dir = "saved_models"
    if arch == 'resnet':
        model_filename = f"resnet18_{dataset_name}.pt"
    else:
        model_filename = f"vovnet_slim19_{dataset_name}.pt"

    if finetune:
        baseline_model_path = os.path.join(model_dir, model_filename)
        dot_pos = model_filename.rfind('.')
        assert dot_pos != -1
        model_filename = f'{model_filename[:dot_pos]}_ft_{finetune_layer_keyword}.{model_filename[dot_pos+1:]}'
        print(f'Finetune dst model_file: {model_filename}')

    set_random_seeds(random_seed=random_seed)

    # Create an untrained model.
    input_ch = 1 if dataset_name == FASHION_MNIST else 3
    model = create_model(num_classes=num_classes, arch=arch, input_ch=input_ch)

    # for name, param in model.named_parameters():
    #     print(f'param name: {name}')
    # exit()

    if finetune:
        print(f'Loading pre-trained weights from {baseline_model_path}')
        model.load_state_dict(torch.load(baseline_model_path))
        for name, param in model.named_parameters():
            if not name.startswith(finetune_layer_keyword):
                param.requires_grad = False
            else:
                print(f'Finetune param: {name}')

    train_loader, test_loader = prepare_dataloader(num_workers=8,
                                                   train_batch_size=128,
                                                   eval_batch_size=256,
                                                   dataset=dataset_name)

    # Train model.
    print("Training Model...")
    model = train_model(model=model,
                        train_loader=train_loader,
                        test_loader=test_loader,
                        device=cuda_device,
                        # device=cpu_device,
                        learning_rate=learning_rate,
                        num_epochs=num_epochs)
    # Save model.
    save_model(model=model, model_dir=model_dir, model_filename=model_filename)


if __name__ == "__main__":
    main()
