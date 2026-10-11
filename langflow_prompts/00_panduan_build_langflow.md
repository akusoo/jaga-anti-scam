# Panduan Build Langflow untuk JAGA

Semua flow dibuat dalam SATU project Langflow bernama "JAGA". Langflow mengekspos satu project sebagai satu MCP server, dan setiap flow di dalamnya menjadi satu tool yang bisa dipanggil Bob.

Ringkasan flow (sesuai build aktual):

| No | Nama flow | Fungsi | Dipanggil Bob? |
|---|---|---|---|
| 1 | jaga_analisis_pesan | Menilai risiko pesan mencurigakan | Ya |
| 2 | jaga_golden_hour | Menyusun langkah darurat dan draft kronologi | Ya |

Selain dua flow itu ada flow kecil "ping" (Chat Input ke Chat Output) yang dipakai untuk smoke test koneksi Bob ke Langflow.

Tidak ada flow ingest dan tidak ada flow kirim email:
- Knowledge base tidak memakai vector database. Isi keempat dokumen di folder knowledge_base digabung dan ditaruh di satu komponen Text Input bernama "Knowledge Base JAGA", lalu disuntikkan ke prompt. Knowledge base JAGA kecil (sekitar 25 KB), jadi seluruh isinya muat di prompt. Hasilnya lebih andal karena tidak ada risiko retrieval mengambil potongan yang salah, dan lebih cepat. Retrieval vector (Astra DB) dipindah ke roadmap, dipakai kalau knowledge base sudah membesar.
- Langflow yang dipakai tidak punya komponen untuk mengirim Gmail. Jadi JAGA tidak mengirim apa pun. Penyimpanan draft kronologi ke file dan penyusunan draft pesan untuk keluarga dilakukan di sisi Bob, dan selalu setelah user setuju (lihat bob/.bob/rules-jaga).

---

## Persiapan

1. Buka Langflow, buat project baru: JAGA
2. Model: JAGA memakai model openai/gpt-oss-120b di Groq lewat komponen Language Model (provider "OpenAI Compatible", karena Groq memakai API format OpenAI). Buat Global Variable OPENAI_COMPATIBLE_BASE_URL = https://api.groq.com/openai/v1 dan OPENAI_COMPATIBLE_API_KEY = API key Groq (gratis di console.groq.com). Awalnya dipakai Gemini free tier, tapi kuota hariannya (20 request per model) habis saat pengujian sehingga dipindah ke Groq yang lebih cepat dan longgar. Simpan API key di Global Variable Langflow (Settings > Global Variables), seperti dua variabel di atas, jangan ditempel langsung di komponen. Ini juga poin keamanan (kredensial di luar flow). Kalau kolom API key di komponen dikosongkan, Langflow memakai variabel global tersebut
3. Siapkan teks knowledge base: gabungkan isi keempat file di folder knowledge_base (01_modus_penipuan, 02_langkah_golden_hour, 03_kontak_resmi, 04_template_kronologi_laporan) menjadi satu teks, urut sesuai nomor file. Tempel ke komponen Text Input "Knowledge Base JAGA" di setiap flow

---

## Flow 1 - jaga_analisis_pesan

Susunan komponen:
- Chat Input (pesan user) tersambung ke variabel {pesan} di Prompt Template
- Text Input "Knowledge Base JAGA" tersambung ke variabel {konteks} di Prompt Template
- Prompt Template -> Language Model (Groq (openai/gpt-oss-120b)) -> Chat Output

Setting Language Model: Provider Override "OpenAI Compatible", Model Name Override "openai/gpt-oss-120b", API key dikosongkan (diambil dari Global Variable), temperature 0.1 supaya konsisten.

Prompt: lihat file 01_flow_analisis_pesan.md

Deskripsi tool untuk MCP (isi lewat pengaturan MCP flow tersebut: aktifkan MCP, isi nama aksi dan deskripsi):
- Nama: jaga_analisis_pesan
- Deskripsi: Menganalisis satu pesan, tautan, atau nama file yang dicurigai penipuan (WhatsApp, SMS, email, DM). Input berupa teks pesan apa adanya. Mengembalikan JSON berisi tingkat_risiko (TINGGI, SEDANG, RENDAH, TIDAK_PASTI), modus, tanda bahaya, penjelasan sederhana, saran tindakan, sumber, dan apakah user perlu mode darurat. Gunakan ketika user bertanya apakah sebuah pesan aman atau penipuan. Jangan gunakan untuk user yang sudah menjadi korban; gunakan jaga_golden_hour.

---

## Flow 2 - jaga_golden_hour

Susunan komponen:
- Chat Input (ringkasan situasi) tersambung ke variabel {situasi} di Prompt Template
- Text Input "Knowledge Base JAGA" (isi sama dengan Flow 1) tersambung ke variabel {konteks}
- Prompt Template -> Language Model (Groq (openai/gpt-oss-120b)) -> Chat Output

Setting Language Model: provider dan model sama dengan Flow 1, temperature 0.2.

Prompt: lihat file 02_flow_golden_hour.md

Deskripsi tool untuk MCP:
- Nama: jaga_golden_hour
- Deskripsi: Mode darurat untuk korban penipuan yang SUDAH terlanjur bertindak (sudah transfer, sudah menginstal APK, sudah memberi OTP/PIN/data kartu, atau akun diambil alih). Input berupa ringkasan situasi: apa yang terjadi, jam kejadian, bank atau e-wallet yang dipakai, nominal jika ada, dan data pelaku yang diketahui. Jangan sertakan PIN, OTP, password, atau nomor rekening korban. Mengembalikan langkah darurat berurutan, kontak resmi yang relevan, draft kronologi laporan IASC, dan checklist bukti.

---

## Expose sebagai MCP server

1. Di halaman Projects, pilih project JAGA, buka tab MCP Server
2. Pastikan hanya flow yang perlu yang aktif sebagai tool: jaga_analisis_pesan dan jaga_golden_hour (flow ping boleh tetap aktif untuk tes)
3. Isi nama dan deskripsi tiap tool persis seperti di atas. Ini penting karena Bob memilih tool berdasarkan deskripsi
4. Salin konfigurasi JSON yang disediakan tab tersebut, lalu tempel ke file `.bob/mcp.json` (lihat folder bob)

---

## Uji tiap flow di Playground sebelum menyambungkan ke Bob

Flow 1, coba input:
"Selamat siang, ini dari kurir J&T, paket atas nama bapak tertahan. Silakan cek foto paketnya di sini: Lihat_Foto_Paket.apk"
Harus keluar tingkat_risiko TINGGI dan modus APK.

Flow 2, coba input:
"Ibu saya baru saja menginstal file undangan pernikahan .apk dari nomor tidak dikenal sekitar jam 19.30, mobile banking BRI ada di HP itu. Belum ada transfer keluar."
Harus keluar langkah Skenario A, nomor BRI dari knowledge base, dan draft kronologi.

Setelah itu jalankan tests/run_eval.py untuk uji otomatis.
