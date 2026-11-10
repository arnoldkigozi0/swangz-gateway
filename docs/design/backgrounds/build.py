import sys,os,random
from PIL import Image,ImageFilter,ImageEnhance,ImageChops
Image.MAX_IMAGE_PIXELS=None
# name: (source id, target mean %, flip)
C={'lamp':(81,34,False,(1.08,1.0,.80)),'hall':(70,36,False,None),'suite':(30,34,False,(1.08,1.0,.82))}
for name,(i,target,flip,grade) in C.items():
    im=Image.open(f'orig/{i}.jpg').convert('RGB')
    w,h=im.size; nh=int(w*9/16)
    if nh<=h: im=im.crop((0,(h-nh)//2,w,(h-nh)//2+nh))
    else: nw=int(h*16/9); im=im.crop(((w-nw)//2,0,(w-nw)//2+nw,h))
    im=im.resize((3840,2160),Image.LANCZOS).filter(ImageFilter.GaussianBlur(26))
    if grade: r,g,b=im.split(); im=Image.merge('RGB',[c.point(lambda v,k=k:min(255,int(v*k))) for c,k in zip((r,g,b),grade)])
    if flip: im=im.transpose(Image.FLIP_LEFT_RIGHT)
    for _ in range(6):
        g=im.resize((64,36)).convert('L').tobytes(); m=sum(g)/len(g)/2.55
        if abs(m-target)<0.7: break
        im=ImageEnhance.Brightness(im).enhance(target/m)
    for wd in (2560,1920,960):
        o=im.resize((wd,wd*9//16),Image.LANCZOS)
        n=Image.effect_noise(o.size,4.4).convert('RGB')   # fine grain so the soft gradients do not band
        o=ImageChops.add(o,n,1,-128)
        f=f'out/room-{name}-{wd}.webp'; o.save(f,'WEBP',quality=86,method=6)
        g=o.resize((64,36)).convert('L').tobytes()
        print(f,os.path.getsize(f)//1024,'KB mean%',round(sum(g)/len(g)/2.55,1))
    im.resize((720,405)).save(f'out/p-{name}.jpg',quality=85)
s=Image.new('RGB',(1440,405*2))
for k,n in enumerate(C): s.paste(Image.open(f'out/p-{n}.jpg'),((k%2)*720,(k//2)*405))
s.save('out/three.jpg',quality=85)
