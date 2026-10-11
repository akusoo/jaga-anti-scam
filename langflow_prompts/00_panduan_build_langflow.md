# Panduan Build Langflow untuk JAGA

Semua flow dibuat dalam SATU project Langflow bernama "JAGA". Alasannya: Langflow mengekspos satu project sebagai satu MCP server, dan setiap flow di dalamnya menjadi satu tool yang bisa dipanggil Bob.

Ringkasan flow:

| No | Nama flow | Fungsi | Dipanggil Bob? |
|---|---|---|---|
| 0 | jaga_ingest_knowledge | Memasukkan 4 dokumen knowledge base ke Astra DB | Tidak (dijalankan manual sekali) |
| 1 | jaga_analisis_pesan | Menilai risiko pesan mencurigakan | Ya |
| 2 | jaga_golden_hour | Menyusun langkah darurat + draft kronologi | Ya |
| 3 | jaga_kirim_email | Mengirim email (ke korban sendiri atau kontak keluarga) | Ya, HANYA setelah user konfirmasi |

Kenapa pengiriman email dipisah jadi flow sendiri: supaya tindakan eksternal tidak bisa terjadi di dalam flow analisis. Bob wajib minta konfirmasi user dulu sebelum memanggil flow 3. Ini poin Responsible AI (human-in-the-loop) yang bisa ditunjukkan langsung di demo dan diagram arsitektur.

---

## Persiapan (15 menit)

1. Buka Langflow, buat project baru: JAGA
2. Siapkan Astra DB (sama seperti hands-on Study Buddy): database, collection bernama `jaga_kb`, dan application token. Simpan token sebagai Global Variable di Langflow (Settings > Global Variables), jangan ditempel langsung di komponen. Ini juga poin keamanan (kredensial di luar flow, slide 33)
3. Model: pakai komponen IBM watsonx.ai kalau kamu punya akses (menambah poin "Integration with IBM technology"). Kalau tidak, pakai provider yang dipakai di hands-on. Embedding juga sama
4. Siapkan koneksi Gmail seperti di hands-on Meeting Action Assistant

---

## Flow 0 - jaga_ingest_knowledge

Susunan komponen:
File (upload 4 file dari folder knowledge_base) -> Split Text -> Astra DB (mode ingest) + Embedding Model

Setting Split Text:
- Chunk size: 1000
- Chunk overlap: 150
- Separator: "---" (dokumen sudah dipisah per modus/skenario dengan garis ini, jadi satu chunk = satu modus utuh)

Jalankan sekali. Cek di Astra DB bahwa dokumen sudah masuk.

---

## Flow 1 - jaga_analisis_pesan

Susunan komponen:
Chat Input -> Astra DB (search, Number of Results: 4) -> Parser -> Prompt Template -> Language Model -> Chat Output
Chat Input juga dihubungkan langsung ke variabel {pesan} di Prompt Template.

Setting Language Model: temperature 0.1 (supaya konsisten).

Prompt: lihat file 01_flow_analisis_pesan.md

Deskripsi tool untuk MCP (isi di Projects > MCP Server > Edit Tools):
- Nama: jaga_analisis_pesan
- Deskripsi: Menganalisis satu pesan, tautan, atau nama file yang dicurigai penipuan (WhatsApp, SMS, email, DM). Input berupa teks pesan apa adanya. Mengembalikan JSON berisi tingkat_risiko (TINGGI, SEDANG, RENDAH, TIDAK_PASTI), modus, tanda bahaya, penjelasan sederhana, saran tindakan, sumber, dan apakah user perlu mode darurat. Gunakan ketika user bertanya apakah sebuah pesan aman atau penipuan. Jangan gunakan untuk user yang sudah menjadi korban; gunakan jaga_golden_hour.

---

## Flow 2 - jaga_golden_hour

Susunan komponen:
Chat Input -> Astra DB (search, Number of Results: 6) -> Parser -> Prompt Template -> Language Model -> Chat Output
Chat Input juga dihubungkan langsung ke variabel {situasi} di Prompt Template.

Setting Language Model: temperature 0.2.

Prompt: lihat file 02_flow_golden_hour.md

Deskripsi tool untuk MCP:
- Nama: jaga_golden_hour
- Deskripsi: Mode darurat untuk korban penipuan yang SUDAH terlanjur bertindak (sudah transfer, sudah menginstal APK, sudah memberi OTP/PIN/data kartu, atau akun diambil alih). Input berupa ringkasan situasi: apa yang terjadi, jam kejadian, bank atau e-wallet yang dipakai, nominal jika ada, dan data pelaku yang diketahui. Jangan sertakan PIN, OTP, password, atau nomor rekening korban. Mengembalikan langkah darurat berurutan, kontak resmi yang relevan, draft kronologi laporan IASC, dan checklist bukti.

---

## Flow 3 - jaga_kirim_email

Susunan komponen (mengikuti pola Meeting Action Assistant):
Chat Input -> Agent (dengan tool Gmail) -> Chat Output

Instruksi Agent: lihat file 03_flow_kirim_email.md

Deskripsi tool untuk MCP:
- Nama: jaga_kirim_email
- Deskripsi: Mengirim email yang SUDAH disetujui user. Input berupa teks dengan format: TO: alamat email, SUBJECT: judul, BODY: isi email. Hanya panggil tool ini setelah user secara eksplisit menyetujui isi email dan penerimanya di percakapan. Tool ini tidak mengubah isi email.

---

## Expose sebagai MCP server

1. Di halaman Projects, pilih project JAGA, buka tab MCP Server
2. Klik Edit Tools, aktifkan hanya flow 1, 2, dan 3 (flow 0 jangan diekspos)
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

Flow 3, coba kirim ke email kamu sendiri dulu.
