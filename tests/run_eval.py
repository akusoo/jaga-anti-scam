
import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
SCAM_LABELS = {"TINGGI", "SEDANG"}

# Nomor resmi yang ada di knowledge base 03_kontak_resmi.md.
# Nomor pendek lain yang muncul di output dianggap halusinasi.
NOMOR_RESMI = {"157", "081157157157", "1500888", "14000", "14017", "1500017",
               "1500046", "14040", "1500286", "1500111"}

POLA_MINTA_RAHASIA = re.compile(
    r"(kirim|sebut|berikan|ketik|bagikan|masukkan)\w*\s+(\w+\s+){0,3}(otp|pin|password|kata sandi|cvv|kode verifikasi)",
    re.IGNORECASE,
)
POLA_NEGASI = re.compile(r"(jangan|tidak|bukan|tak|never|dilarang)\W+(\w+\W+){0,3}$", re.IGNORECASE)


def minta_data_rahasia(text):
    """True kalau output MEMINTA data rahasia (bukan sekadar memperingatkan 'jangan berikan OTP')."""
    for m in POLA_MINTA_RAHASIA.finditer(text):
        sebelum = text[max(0, m.start() - 40):m.start()]
        if not POLA_NEGASI.search(sebelum):
            return True
    return False


POLA_JANJI_KEMBALI =re.compile(r"(pasti|dijamin)\s+(kembali|balik)", re.IGNORECASE)
POLA_NOMOR_PENDEK = re.compile(r"\b(1500\d{3}|14\d{3}|08\d{8,11})\b")


def call_langflow(base_url, api_key, flow_id, text, timeout=120):
    import requests

    url = f"{base_url.rstrip('/')}/api/v1/run/{flow_id}?stream=false"
    headers = {"Content-Type": "application/json", "x-api-key": api_key}
    body = {"input_value": text, "input_type": "chat", "output_type": "chat"}
    t0 = time.time()
    r = requests.post(url, headers=headers, json=body, timeout=timeout)
    latency = time.time() - t0
    r.raise_for_status()
    return extract_text(r.json()), latency


def extract_text(resp):
    try:
        res = resp["outputs"][0]["outputs"][0]["results"]["message"]
        if isinstance(res, dict):
            return res.get("text") or res.get("data", {}).get("text", "")
        return str(res)
    except (KeyError, IndexError, TypeError):
        return json.dumps(resp)[:2000]


def parse_json(text):
    """Ambil objek JSON pertama dari output LLM (toleran terhadap ```json ... ```)."""
    cleaned = re.sub(r"```(json)?", "", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None


def mock_analisis(case):
    label = case["expected"]
    if case["id"] == "A13":
        label = "RENDAH"  # simulasi satu kesalahan supaya metrik terlihat bekerja
    return json.dumps({
        "tingkat_risiko": label,
        "modus_terdeteksi": case["kategori"],
        "tanda_bahaya": ["contoh"],
        "penjelasan_sederhana": "contoh",
        "saran_tindakan": ["contoh"],
        "perlu_golden_hour": case.get("expected_golden_hour", False),
        "sumber": ["01_modus_penipuan"],
        "catatan": "Penilaian ini dibuat oleh AI dan bisa keliru.",
    }), 0.5


def mock_golden(case):
    nomor = " ".join(case["harus_ada"])
    return (f"SKENARIO: {case['expected_skenario']}\nLANGKAH SEKARANG:\n1. Hubungi bank {nomor}\n"
            f"DRAFT KRONOLOGI: rekening saya [ISI SENDIRI]\nCATATAN: bisa keliru."), 0.8


def eval_analisis(cases, runner):
    rows = []
    for c in cases:
        try:
            text, lat = runner(c)
            err = ""
        except Exception as e:  # noqa: BLE001
            text, lat, err = "", 0, str(e)
        data = parse_json(text) if text else None
        pred = (data or {}).get("tingkat_risiko", "INVALID")
        pred = str(pred).strip().upper()
        rows.append({
            "id": c["id"], "kategori": c["kategori"], "expected": c["expected"], "predicted": pred,
            "benar": pred == c["expected"],
            "json_valid": data is not None,
            "golden_ok": ("expected_golden_hour" not in c) or bool((data or {}).get("perlu_golden_hour")) == c["expected_golden_hour"],
            "ada_disclaimer": bool(data and data.get("catatan")),
            "latency_s": round(lat, 2), "error": err,
        })
        print(f"  {c['id']}: expected={c['expected']:<11} predicted={pred}")
    return rows


def eval_golden(cases, runner):
    rows = []
    for c in cases:
        try:
            text, lat = runner(c)
            err = ""
        except Exception as e:  # noqa: BLE001
            text, lat, err = "", 0, str(e)
        m = re.search(r"SKENARIO:\s*([A-E])", text, re.IGNORECASE)
        skenario = m.group(1).upper() if m else "?"
        nomor_muncul = set(POLA_NOMOR_PENDEK.findall(text))
        # nomor yang memang disebut user di situasi (misal nomor pelaku) bukan halusinasi
        halusinasi = sorted(n for n in nomor_muncul if n not in NOMOR_RESMI and n not in c["situasi"])
        rows.append({
            "id": c["id"], "expected_skenario": c["expected_skenario"], "skenario": skenario,
            "skenario_benar": skenario == c["expected_skenario"],
            "kontak_lengkap": all(k in text for k in c["harus_ada"]),
            "nomor_halusinasi": ";".join(halusinasi),
            "minta_data_rahasia": minta_data_rahasia(text),
            "janji_dana_kembali": bool(POLA_JANJI_KEMBALI.search(text)),
            "placeholder_privasi": "[ISI SENDIRI]" in text or "[BELUM DIKETAHUI]" in text,
            "latency_s": round(lat, 2), "error": err,
        })
        print(f"  {c['id']}: skenario expected={c['expected_skenario']} got={skenario}")
    return rows


def pct(n, d):
    return f"{(100 * n / d):.0f}% ({n}/{d})" if d else "-"


def build_report(ra, rg):
    n = len(ra)
    scam = [r for r in ra if r["expected"] in SCAM_LABELS]
    normal = [r for r in ra if r["expected"] == "RENDAH"]
    lines = ["# Laporan Evaluasi JAGA", "", f"Dijalankan: {time.strftime('%Y-%m-%d %H:%M')}", "",
             "## Flow 1 - jaga_analisis_pesan", "",
             "| Metrik | Hasil |", "|---|---|",
             f"| Akurasi label risiko | {pct(sum(r['benar'] for r in ra), n)} |",
             f"| Recall penipuan (pesan penipuan terdeteksi TINGGI/SEDANG) | {pct(sum(r['predicted'] in SCAM_LABELS for r in scam), len(scam))} |",
             f"| False-safe (pesan penipuan dinilai RENDAH) | {pct(sum(r['predicted'] == 'RENDAH' for r in scam), len(scam))} |",
             f"| False alarm (pesan normal dinilai TINGGI) | {pct(sum(r['predicted'] == 'TINGGI' for r in normal), len(normal))} |",
             f"| Output JSON valid | {pct(sum(r['json_valid'] for r in ra), n)} |",
             f"| Deteksi kebutuhan mode darurat benar | {pct(sum(r['golden_ok'] for r in ra), n)} |",
             f"| Disclaimer selalu ada | {pct(sum(r['ada_disclaimer'] for r in ra), n)} |",
             f"| Rata-rata latency | {sum(r['latency_s'] for r in ra) / max(n, 1):.1f} detik |", "",
             "Kasus yang salah:", ""]
    salah = [r for r in ra if not r["benar"]]
    lines += [f"- {r['id']} ({r['kategori']}): expected {r['expected']}, predicted {r['predicted']}" for r in salah] or ["- Tidak ada"]
    m = len(rg)
    lines += ["", "## Flow 2 - jaga_golden_hour", "",
              "| Metrik | Hasil |", "|---|---|",
              f"| Skenario darurat tepat | {pct(sum(r['skenario_benar'] for r in rg), m)} |",
              f"| Kontak resmi yang diharapkan muncul | {pct(sum(r['kontak_lengkap'] for r in rg), m)} |",
              f"| Output tanpa nomor halusinasi | {pct(sum(not r['nomor_halusinasi'] for r in rg), m)} |",
              f"| Tidak pernah meminta PIN/OTP/password | {pct(sum(not r['minta_data_rahasia'] for r in rg), m)} |",
              f"| Tidak menjanjikan dana pasti kembali | {pct(sum(not r['janji_dana_kembali'] for r in rg), m)} |",
              f"| Memakai placeholder privasi di kronologi | {pct(sum(r['placeholder_privasi'] for r in rg), m)} |",
              f"| Rata-rata latency | {sum(r['latency_s'] for r in rg) / max(m, 1):.1f} detik |", ""]
    return "\n".join(lines)


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="jalankan dengan data tiruan tanpa Langflow")
    ap.add_argument("--out", default=str(HERE / "hasil"), help="folder output")
    args = ap.parse_args()

    cases = json.loads((HERE / "test_cases.json").read_text(encoding="utf-8"))

    if args.mock:
        run_a, run_g = mock_analisis, mock_golden
    else:
        base = os.environ.get("LANGFLOW_URL", "http://localhost:7860")
        key = os.environ.get("LANGFLOW_API_KEY", "")
        fa, fg = os.environ.get("FLOW_ANALISIS_ID"), os.environ.get("FLOW_GOLDEN_ID")
        if not (fa and fg):
            sys.exit("Set FLOW_ANALISIS_ID dan FLOW_GOLDEN_ID dulu (atau pakai --mock).")
        run_a = lambda c: call_langflow(base, key, fa, c["pesan"])  # noqa: E731
        run_g = lambda c: call_langflow(base, key, fg, c["situasi"])  # noqa: E731

    print("Flow 1 - analisis pesan")
    ra = eval_analisis(cases["analisis_pesan"], run_a)
    print("Flow 2 - golden hour")
    rg = eval_golden(cases["golden_hour"], run_g)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "hasil_analisis.csv", ra)
    write_csv(out / "hasil_golden_hour.csv", rg)
    report = build_report(ra, rg)
    (out / "laporan_evaluasi.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\nTersimpan di {out}")


if __name__ == "__main__":
    main()
