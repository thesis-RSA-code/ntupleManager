import h5py, time
F="/sps/t2k/eleblevec/Datasets/sk_iv/pgun_ccan/electron/h5/sk_pgun_ccan_e-_0.11_pe.h5"
t=time.time()
with h5py.File(F,"r") as f:
    autres=[]; n_ev=0; mx=-1
    for k in f.keys():
        if k.startswith("event_"):
            n_ev+=1
            try: mx=max(mx,int(k.split("_")[1]))
            except: autres.append(k)
        else:
            autres.append((k, type(f[k]).__name__))
    print("cles totales      : %d" % (n_ev+len(autres)))
    print("groupes event_*   : %d  (indice max = %d)" % (n_ev, mx))
    print("objets NON-event  : %d -> %s" % (len(autres), autres[:10]))
    print("attribut n_events : %s" % dict(f.attrs).get("n_events"))
print("[%.0f s]" % (time.time()-t))