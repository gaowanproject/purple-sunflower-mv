import numpy as np, wave, json, os
p = os.path.abspath("assets/audio/song.wav")
w = wave.open(p, 'rb')
sr = w.getframerate(); n = w.getnframes(); ch = w.getnchannels()
raw = w.readframes(n); w.close()
x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
x = x.reshape(-1, ch).mean(axis=1)
dur = len(x)/sr
print(f"DUR {dur:.3f}s  sr={sr} samples={len(x)}")
# ---- RMS envelope, 10ms hop
hop = int(sr*0.01); nfr = len(x)//hop
rms = np.array([np.sqrt(np.mean(x[i*hop:(i+1)*hop]**2)+1e-12) for i in range(nfr)])
db = 20*np.log10(rms+1e-9)
print("RMS dB range: min %.1f max %.1f p95 %.1f" % (db.min(), db.max(), np.percentile(db,95)))
# find last loud region
thr = db.max() - 45
loud = np.where(db > thr)[0]
print("first loud %.2fs last loud %.2fs" % (loud[0]*0.01, loud[-1]*0.01))
# near-end levels
for t in [dur-1, dur-3, dur-5, dur-8, dur-10, dur-15, dur-20]:
    i = int(t/0.01)
    if 0 <= i < nfr: print("  t=%.1fs db=%.1f" % (t, db[i]))
# ---- STFT spectral flux for onsets
N=2048; H=512
win = np.hanning(N).astype(np.float32)
nf = (len(x)-N)//H
S = np.zeros((nf, N//2+1), dtype=np.float32)
for i in range(nf):
    f = np.fft.rfft(x[i*H:i*H+N]*win)
    S[i] = np.abs(f)
S = np.log1p(S*10)
flux = np.zeros(nf, dtype=np.float32)
flux[1:] = np.maximum(0, np.diff(S, axis=0)).sum(axis=1)
flux /= (flux.max()+1e-9)
# smooth
k = np.hanning(9); k/=k.sum()
flux_s = np.convolve(flux, k, mode='same')
# peak pick
diff = np.diff(flux_s)
peaks = []
for i in range(2, nf-2):
    if flux_s[i] > flux_s[i-1] and flux_s[i] >= flux_s[i+1] and flux_s[i] > 0.12:
        if flux_s[i] >= flux_s[i-2] and flux_s[i] >= flux_s[i+2]:
            peaks.append(i)
# merge close peaks (min 0.12s)
merged=[]
for i in peaks:
    t=i*H/sr
    if not merged or t-merged[-1] > 0.12: merged.append(t)
print("ONSETS", len(merged))
# ---- tempo estimate from onset autocorrelation
if len(merged)>8:
    env = np.zeros(int(dur*100))
    for t in merged: 
        j=int(t*100); env[j]=1
    ac = np.correlate(env, env, 'full')[len(env)-1:]
    lags = np.arange(len(ac))*0.01
    mask = (lags>0.3)&(lags<1.2)
    best = lags[mask][np.argmax(ac[mask])]
    print("BPM approx %.1f (lag %.2fs)" % (60/best, best))
# ---- energy sections: 1s blocks
blk = sr
secs=[]
for s0 in range(0, len(x)-blk, blk):
    seg = x[s0:s0+blk]
    secs.append(20*np.log10(np.sqrt(np.mean(seg**2))+1e-9))
print("SEC energy per second (dB):")
print(" ".join(f"{v:.0f}" for v in secs))
json.dump({"duration":dur,"sr":sr,"onsets":merged}, open("assets/audio/audio_meta.json","w"))
np.save("assets/audio/rms.npy", rms); np.save("assets/audio/onsets.npy", np.array(merged))
