#!/usr/bin/env python3
"""Скачать модели один раз в ./models/ (запускать у себя, не в репо).
Дальше страница работает без huggingface.co: transformers.js читает только ./models/.
v2 (2026-11-08): ревизия HF фиксируется. При первом прогоне для каждого репо
берётся текущий sha и пишется в models/MANIFEST.sha256 строкой "# revision <repo> <sha>";
повторные прогоны докачивают строго ту же ревизию (копии воспроизводимы и
torrent-совместимы), даже если main в HF уже ушёл вперёд. --pin SHA задаёт ревизию явно.
v2 также не качает лишнее: pipeline(transformers.js, dtype q8) для seq2seq грузит
encoder_model_quantized + decoder_model_merged_quantized; раздельные
decoder_model_quantized / decoder_with_past_model_quantized дублируют merged и
пропускаются (замер 2026-11-08: mt 1747→854 МБ, whisper-tiny 100→41 МБ).
Использование:
  python3 tools/fetch_models.py [--dest models] [--set mt asr-tiny asr-base asr-small] [--pin SHA]
Только stdlib, без токенов и pip. Для каждого файла пишет sha256 в models/MANIFEST.sha256 —
так копию можно раздать торрентом и проверить на любой машине."""
import argparse, hashlib, json, os, sys, urllib.request, urllib.parse

SETS = {
    "mt":        ["Xenova/nllb-200-distilled-600M"],      # перевод, 200 языков (~600 МБ в q8)
    "asr-tiny":  ["onnx-community/whisper-tiny"],         # ~45 МБ
    "asr-base":  ["onnx-community/whisper-base"],         # ~85 МБ
    "asr-small": ["onnx-community/whisper-small"],        # ~250 МБ
}
API_INFO = "https://huggingface.co/api/models/{repo}"
API_TREE = "https://huggingface.co/api/models/{repo}/tree/{rev}?recursive=1"
RAW = "https://huggingface.co/{repo}/resolve/{rev}/{path}"

def want(path):
    if path.endswith((".safetensors", ".bin", ".h5", ".msgpack", ".md", ".gitattributes")): return False
    if path.startswith("onnx/"):
        # q8 в transformers.js = *_quantized.onnx ; остальные варианты не нужны
        return path.endswith("_quantized.onnx")
    return True

def minimal(paths):
    """transformers.js для seq2seq (pipeline, q8) грузит encoder + merged-декодер;
    раздельные decoder_model/decoder_with_past не нужны — пропускать."""
    if any(p.endswith("decoder_model_merged_quantized.onnx") for p in paths):
        drop = {"decoder_model_quantized.onnx", "decoder_with_past_model_quantized.onnx"}
        paths = [p for p in paths if os.path.basename(p) not in drop]
    return paths

def get(url, out=None):
    req = urllib.request.Request(url, headers={"User-Agent": "fetch_models/2"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if out is None: return r.read()
        h = hashlib.sha256()
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out + ".part", "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b: break
                f.write(b); h.update(b)
        os.replace(out + ".part", out)
        return h.hexdigest()

def file_sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def manifest_revs(dest):
    """Ревизии из прошлого прогона: строки '# revision <repo> <sha>'."""
    revs = {}
    p = os.path.join(dest, "MANIFEST.sha256")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            parts = line.split()
            if len(parts) == 4 and parts[0:2] == ["#", "revision"]:
                revs[parts[2]] = parts[3]
    return revs

def main():
    try: sys.stdout.reconfigure(errors="replace")
    except AttributeError: pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="models")
    ap.add_argument("--set", nargs="+", default=["mt", "asr-tiny"], choices=list(SETS))
    ap.add_argument("--pin", default=None, help="зафиксировать ревизию HF (sha) явно")
    a = ap.parse_args()
    pinned = manifest_revs(a.dest)
    manifest, rev_lines = {}, []
    for s in a.set:
        for repo in SETS[s]:
            rev = a.pin or pinned.get(repo)
            if not rev:
                rev = json.loads(get(API_INFO.format(repo=repo)))["sha"]
                print(f"{repo}: фиксирую ревизию {rev[:12]}")
            rev_lines.append(f"# revision {repo} {rev}")
            tree = json.loads(get(API_TREE.format(repo=repo, rev=rev)))
            files = [t["path"] for t in tree if t["type"] == "file" and want(t["path"])]
            files = minimal(files)
            print(f"{repo} @ {rev[:12]}: {len(files)} файлов")
            for p in files:
                out = os.path.join(a.dest, repo, p)
                if os.path.exists(out):
                    h = file_sha256(out)
                else:
                    print("  ↓", p); h = get(RAW.format(repo=repo, rev=rev, path=urllib.parse.quote(p)), out)
                manifest[os.path.join(repo, p)] = h
    with open(os.path.join(a.dest, "MANIFEST.sha256"), "w", encoding="utf-8") as f:
        for line in rev_lines: f.write(line + "\n")
        for k, v in sorted(manifest.items()): f.write(f"{v}  {k}\n")
    print("готово:", len(manifest), "файлов, манифест записан (ревизии зафиксированы)")

if __name__ == "__main__":
    try: main()
    except Exception as e: sys.exit(f"ошибка: {e}")
