import json, os, numpy as np
md_path = r'rag_data/metadata.json'
emb_path = r'rag_data/embeddings.npy'
print('Files:')
for p in (md_path, emb_path, 'rag_data/faiss.index', 'rag_data/metadata.parquet'):
    try:
        s=os.path.getsize(p)
        print(f'  {p}: {s:,} bytes')
    except Exception as e:
        print(f'  {p}: not found')

with open(md_path,'r',encoding='utf-8') as f:
    md = json.load(f)
print('\nMetadata entries:', len(md))
print('Sample metadata keys:', list(md[0].keys())[:10])

emb = np.load(emb_path)
print('\nEmbeddings shape:', getattr(emb,'shape',None), 'dtype=', getattr(emb,'dtype',None))
print('First embedding norm: %.4f' % (np.linalg.norm(emb[0]),))
print('Embedding sample (first 5 elements):', emb[0][:5].tolist())
