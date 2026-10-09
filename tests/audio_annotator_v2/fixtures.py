"""Generate deterministic synthetic native-rate fixtures; no private audio is included.

The optional large fixtures need about 550 MB of physical disk on a sparse-file
filesystem, but have roughly 7.5 GB of logical size. Other filesystems may allocate
that full logical size. Existing fixtures are retained unless --overwrite is used.
"""
from pathlib import Path
import argparse
import struct
import numpy as np
import soundfile as sf


def generate(root: Path, large: bool = False, overwrite: bool = False) -> None:
    root.mkdir(parents=True, exist_ok=True)

    def missing(name):
        return overwrite or not (root / name).exists()

    rate = 384000
    t = np.arange(rate * 2) / rate
    stereo = np.column_stack((.5*np.sin(2*np.pi*100000*t) + .08*np.sin(2*np.pi*1000*t), .4*np.sin(2*np.pi*150000*t)))
    for subtype in ['PCM_U8', 'PCM_16', 'PCM_24', 'PCM_32', 'FLOAT', 'DOUBLE']:
        name = 'ultrasonic_' + subtype + '.wav'
        if missing(name):
            sf.write(root / name, stereo, rate, subtype=subtype)
    for channels in [1, 2, 4]:
        name = f'flac_{channels}ch_24bit.flac'
        if missing(name):
            samples = np.column_stack([.4*np.sin(2*np.pi*21000*(c+1)*t) for c in range(channels)])
            sf.write(root / name, samples, rate, subtype='PCM_24')
    for name, rate, freq in [('native_768k.wav', 768000, 250000), ('native_1536k.wav', 1536000, 400000)]:
        if missing(name):
            sf.write(root / name, .5*np.sin(2*np.pi*freq*np.arange(rate)/rate), rate, subtype='PCM_24')
    if missing('medium_55s.wav'):
        rate = 96000
        with sf.SoundFile(root/'medium_55s.wav', 'w', samplerate=rate, channels=1, subtype='PCM_16') as f:
            for second in range(55):
                t = (np.arange(rate) + second*rate) / rate
                f.write(.5*np.sin(2*np.pi*12000*t))
    if missing('flac_residuals.flac'):
        rng = np.random.default_rng(31)
        a = np.concatenate([np.zeros(8192), np.full(8192, .123), rng.uniform(-.8,.8,8192), .4*np.sin(np.arange(8192))])
        sf.write(root/'flac_residuals.flac', np.column_stack((a,a[::-1])), 96000, subtype='PCM_16')
    if not large:
        return
    if missing('sparse_4_8GB_rf64.wav'):
        rate, channels, frames = 384000, 2, 1200000000
        size = frames * channels * 2
        header = b'RF64' + struct.pack('<I',0xffffffff) + b'WAVE'
        header += b'ds64' + struct.pack('<IQQQI',28,size+72,size,frames,0)
        header += b'fmt ' + struct.pack('<IHHIIHH',16,1,channels,rate,rate*channels*2,channels*2,16)
        header += b'data' + struct.pack('<I',0xffffffff)
        assert len(header) == 80
        with (root/'sparse_4_8GB_rf64.wav').open('wb') as f:
            f.write(header); f.truncate(80+size)
            for frame in [0,frames//2,frames-1]:
                f.seek(80+frame*4); f.write(struct.pack('<hh',12345,-23456))
    if missing('sparse_2145MB.wav'):
        total, rate = 2145570362, 96000
        data_size = total-54
        header = b'RIFF'+struct.pack('<I',total-8)+b'WAVEfmt '+struct.pack('<IHHIIHH',16,1,1,rate,rate*2,2,16)+b'data'+struct.pack('<I',data_size)
        with (root/'sparse_2145MB.wav').open('wb') as f:
            f.write(header);f.seek(44+data_size);f.write(b'JUNK'+struct.pack('<I',2)+b'\0\0')
    if missing('large_noise_7min.flac'):
        rng = np.random.default_rng(83)
        frames = 192000*420
        with sf.SoundFile(root/'large_noise_7min.flac','w',samplerate=192000,channels=2,subtype='PCM_24') as f:
            for start in range(0,frames,131072):
                f.write(rng.uniform(-.9,.9,size=(min(131072,frames-start),2)).astype('float32'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--large', action='store_true')
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    generate(args.directory, args.large, args.overwrite)
    for p in sorted(args.directory.iterdir()):
        if p.is_file():
            print(p.name, p.stat().st_size)
