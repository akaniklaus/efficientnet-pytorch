import torch
import torch.nn as nn
import torch.nn.functional as F

from .swish import Swish

#TODO: stochastic depth

class SqeezeExcitation(nn.Module):
    def __init__(self, inplanes, se_ratio):
        super(SqeezeExcitation, self).__init__()
        hidden_dim = int(inplanes*se_ratio)
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.fc1 = nn.Linear(inplanes, hidden_dim, bias=False)
        self.fc2 = nn.Linear(hidden_dim, inplanes, bias=False)
        self.swish = Swish()
        self.sigmoid = nn.Sigmoid()
    def forward(self, x):
        out = self.avg_pool(x).view(x.size(0), -1)
        out = self.swish(self.fc1(out))
        out = self.sigmoid(self.fc2(out))
        out = out.unsqueeze(2).unsqueeze(3)
        return x * out.expand_as(x)

class Bottleneck(nn.Module):
    def __init__(self,inplanes, planes, kernel_size, stride, expand, se_ratio):
        super(Bottleneck, self).__init__()
        if expand != 1:
            self.conv1 = nn.Sequential(nn.Conv2d(inplanes, inplanes*expand, kernel_size=1, bias=False),
                                       nn.BatchNorm2d(inplanes*expand, momentum=0.99, eps=1e-3), Swish())
        self.conv2 = nn.Conv2d(inplanes*expand, inplanes*expand, kernel_size=kernel_size, stride=stride,
                               padding=kernel_size//2, groups=inplanes*expand, bias=False)
        self.bn2 = nn.BatchNorm2d(inplanes*expand, momentum=0.99, eps=1e-3)
        self.se = SqeezeExcitation(inplanes*expand, se_ratio)
        self.conv3 = nn.Sequential(nn.Conv2d(inplanes*expand, planes, kernel_size=1, bias=False),
                                   nn.BatchNorm2d(planes, momentum=0.99, eps=1e-3))
        self.swish = Swish()
        self.correct_dim = (stride == 1) and (inplanes == planes)

    def forward(self, x):
        out = self.conv1(x) if hasattr(self, 'conv1') else x
        out = self.swish(self.bn2(self.conv2(out)))
        out = self.conv3(self.se(out))
        if self.correct_dim: out += x
        return self.swish(out)

class MBConv(nn.Module):
    def __init__(self, inplanes, planes, repeat, kernel_size, stride, expand, se_ratio):
        super(MBConv, self).__init__()
        layer = []

        layer.append(Bottleneck(inplanes, planes, kernel_size, stride, expand, se_ratio))
        for _ in range(1, repeat):
            layer.append(Bottleneck(planes, planes, kernel_size, 1, expand, se_ratio))

        self.layer = nn.Sequential(*layer)

    def forward(self, x):
        return self.layer(x)

class Flatten(nn.Module):
    def __init(self):
        super(Flatten, self).__init__()
    def forward(self, x):
        return x.view(x.size(0), -1)

class EfficientNet(nn.Module):
    def __init__(self, num_classes=1000, width_coef=1., depth_coef=1., scale=1.,dropout_ratio=0.2, se_ratio=0.25):
        super(EfficientNet, self).__init__()
        channels = [32, 16, 24, 40, 80, 112, 192, 320, 1280]
        expands = [1, 6, 6, 6, 6, 6, 6]
        repeats = [1, 2, 2, 3, 3, 4, 1]
        strides = [1, 2, 2, 2, 1, 2, 1]
        depth = depth_coef
        width = width_coef
        self.scale = scale

        channels = [round(x*width) for x in channels] # [int(x*width) for x in channels]
        repeats = [round(x*depth) for x in repeats] # [int(x*width) for x in repeats]

        self.inn = nn.Sequential(
            nn.Conv2d(3, channels[0], kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(channels[0], momentum=0.99, eps=1e-3), Swish())
        
        blocks = []
        for _ in range(7):
            blocks.append(MBConv(channels[i], channels[i], repeats[i], kernel_size=3,
                         stride=strides[i], expand=expands[i], se_ratio=se_ratio))
        self.stages = nn.Sequential(*blocks)
        
        self.out = nn.Sequential(
                            nn.Conv2d(channels[7], channels[8], kernel_size=1, bias=False),
                            nn.BatchNorm2d(channels[8], momentum=0.99, eps=1e-3), Swish(),
                            nn.AdaptiveAvgPool2d((1, 1)), Flatten(), nn.Dropout(p=dropout_ratio),
                            nn.Linear(channels[8], num_classes))

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                # nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='sigmoid')
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

    def forward(self, x):
        if self.scale > 1.0:
            x = F.interpolate(x, scale_factor=self.scale, 
                mode='bilinear', align_corners=False)
        return self.out(self.stages(self.inn(x)))

def efficientnet_b0(num_classes=1000):
    return EfficientNet(num_classes=num_classes, width_coef=1.0, depth_coef=1.0, scale=1.0,dropout_ratio=0.2, se_ratio=0.25)

def efficientnet_b1(num_classes=1000):
    return EfficientNet(num_classes=num_classes, width_coef=1.0, depth_coef=1.1, scale=240/224, dropout_ratio=0.2, se_ratio=0.25)

def efficientnet_b2(num_classes=1000):
    return EfficientNet(num_classes=num_classes, width_coef=1.1, depth_coef=1.2, scale=260/224., dropout_ratio=0.3, se_ratio=0.25)

def efficientnet_b3(num_classes=1000):
    return EfficientNet(num_classes=num_classes, width_coef=1.2, depth_coef=1.4, scale=300/224, dropout_ratio=0.3, se_ratio=0.25)

def efficientnet_b4(num_classes=1000):
    return EfficientNet(num_classes=num_classes, width_coef=1.4, depth_coef=1.8, scale=380/224, dropout_ratio=0.4, se_ratio=0.25)

def efficientnet_b5(num_classes=1000):
    return EfficientNet(num_classes=num_classes, width_coef=1.6, depth_coef=2.2, scale=456/224, dropout_ratio=0.4, se_ratio=0.25)

def efficientnet_b6(num_classes=1000):
    return EfficientNet(num_classes=num_classes, width_coef=1.8, depth_coef=2.6, scale=528/224, dropout_ratio=0.5, se_ratio=0.25)

def efficientnet_b7(num_classes=1000):
    return EfficientNet(num_classes=num_classes, width_coef=2.0, depth_coef=3.1, scale=600/224, dropout_ratio=0.5, se_ratio=0.25)

def test():
    x = torch.FloatTensor(64, 3, 224, 224)
    model = efficientnet_b3()
    logit = model(x)
    print(logit.size())

if __name__ == '__main__':
    test()
