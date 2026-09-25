# WISE AI

**Waste Intelligence System for Efficiency** adalah prototipe aplikasi web untuk membantu supermarket dan pasar modern mengidentifikasi produk yang berisiko menjadi *food waste*. Aplikasi mengolah data stok dan penjualan, memperkirakan probabilitas *waste* dengan model machine learning, lalu menyajikan rekomendasi tindakan dan ringkasan analitik bagi pengelola.

> **Status proyek:** prototipe dengan alur data, peninjauan rekomendasi, pencatatan hasil manual, mode operasional dengan login dan akses cabang, serta pemantauan distribusi prediksi. Evaluasi berlabel tersedia sebagai alat CLI, tetapi belum ada hasil validasi independen pada data operasional. Mode lokal tetap terbuka untuk demo; `serve.py` mewajibkan autentikasi dan konfigurasi keamanan.

## Tujuan produk

WISE AI membantu pengelola menjawab tiga pertanyaan:

1. Produk mana yang paling berisiko terbuang?
2. Tindakan apa yang dapat dipertimbangkan sebelum produk kedaluwarsa?
3. Cabang dan kategori mana yang memerlukan perhatian lebih besar?

Pengguna utama yang dituju adalah pengelola stok, manajer cabang, dan tim operasional retail. Hasil prediksi merupakan alat bantu keputusan, bukan bukti bahwa *waste* telah berkurang atau instruksi yang otomatis dijalankan.

## Fitur yang tersedia

| Fitur | Fungsi | Lokasi |
| --- | --- | --- |
| Landing page | Menjelaskan masalah, tujuan produk, dan fitur WISE AI. | `/` |
| Quick Demo | Menerima data numerik satu produk dan menampilkan probabilitas serta tingkat risiko *food waste*. | Form pada `/`, API `POST /api/predict` |
| Prediksi dataset | Memproses seluruh baris dataset Excel menggunakan model tersimpan dan memberi label risiko `Low`, `Medium`, atau `High`. | Pipeline backend untuk dashboard dan API data |
| Rekomendasi tindakan | Menghasilkan saran persentase diskon, redistribusi, donasi, dan promosi resep berdasarkan aturan. Dashboard saat ini menampilkan diskon, redistribusi, dan donasi. | Pipeline backend dan `/dashboard` |
| Dashboard KPI | Menampilkan jumlah produk, jumlah produk berisiko tinggi, dan akumulasi *waste* historis apabila datanya tersedia. | `/dashboard` |
| Produk kritis | Menampilkan seluruh produk berisiko `High` dalam tabel yang dapat digulir, diurutkan menurut probabilitas *waste*. | `/dashboard` |
| Alert produk | Menampilkan seluruh produk yang mendekati kedaluwarsa atau berisiko `High` dalam panel yang dapat digulir. | `/dashboard` |
| Analitik cabang dan kategori | Menampilkan tabel dan grafik batang probabilitas *waste* rata-rata per cabang dan kategori, serta metrik stok terkait. Grafik dirender langsung oleh server. | `/dashboard` |
| API data | Menyediakan produk kritis, alert, performa cabang, dan efisiensi stok dalam format JSON. | `/api/data/*` |
| Import data | Memvalidasi CSV/XLSX, menjalankan analisis, lalu menyimpan hasil sebagai dataset aktif. Impor yang gagal tidak mengganti data sebelumnya. | `/upload` |
| Riwayat impor | Mencatat nama file, waktu UTC, jumlah baris, dan batch aktif di SQLite. | `/upload` |
| Export hasil | Mengunduh dataset aktif bersama prediksi dan rekomendasi sebagai XLSX. | `/export` |
| Pencarian produk | Mencari ID atau nama, memfilter cabang, kategori, dan risiko, serta menampilkan 25 produk per halaman. | `/products` |
| Detail dan peninjauan | Melihat data input, probabilitas, rekomendasi per tindakan, lalu mencatat keputusan dan catatan untuk produk dari batch aktif. | `/products/<import_id>/<row_number>` |
| Hasil operasional | Mencatat unit terjual, didonasikan, dipindahkan, dan terbuang setelah impor; nilai rupiah opsional. Edit tersimpan dalam riwayat. | Detail produk batch aktif |
| Laporan hasil | Melihat total, tren tanggal, ringkasan cabang, dan catatan produk untuk satu batch. | `/reports` |
| Akun operasional | Landing page terbuka, lalu petugas dapat Sign up dengan password pilihannya. Admin menyetujui cabang sebelum akun dapat Sign in. Data dashboard, produk, laporan, dan API data dibatasi sesuai cabang akun. | `/`, `/signup`, `/login` |
| Panel admin | Meninjau pendaftaran, melihat akun dan aktivitas impor, membuat akun petugas cabang atau admin, serta memperbarui password/peran akun. | `/admin` |
| Akun saya | Admin dan petugas cabang dapat mengganti password sendiri setelah masuk. | `/account` |
| Pemeriksaan layanan | Respons liveness sederhana untuk pemantauan tanpa membuka data bisnis. | `/health` |
| Pemantauan model | Membandingkan proporsi risiko, skor rata-rata, jumlah produk, dan versi artefak model pada 12 batch impor terbaru. | `/model-monitoring` |
| Evaluasi berlabel | Menghitung metrik klasifikasi dan kalibrasi dari file CSV/XLSX berlabel `Waste_Flag` yang disediakan terpisah. | `evaluate_model.py` |

### Cara kerja prediksi

```text
CSV/XLSX hasil upload (atau dataset contoh sebelum upload pertama)
    → pemilihan fitur model
    → prediksi probabilitas waste
    → klasifikasi risiko
    → rekomendasi berbasis aturan
    → penyimpanan SQLite untuk upload
    → dashboard / API JSON / export XLSX
```

Model menggunakan delapan input: `Initial_Stock`, `Sold_Quantity`, `Remaining_Stock`, `Expiry_Days_Left`, `Price`, `Discount_Applied`, `Temperature_(°C)`, dan `Historical_Avg_Sales`. Label risiko ditentukan dari probabilitas model: `High` mulai 0,7; `Medium` mulai 0,4; selain itu `Low`. Nama kolom temperatur pada dataset dan konfigurasi harus sama persis; periksa ejaan serta encoding karakter `°` sebelum memakai data baru.

Rekomendasi saat ini berasal dari aturan di `wise_ai/recommendation_system.py`, bukan dari model ML terpisah. Contohnya, produk berisiko tinggi dapat memperoleh saran diskon 30% atau 40%, sedangkan saran donasi muncul ketika risiko tinggi dan masa berlaku tersisa paling banyak dua hari. Rekomendasi belum memperhitungkan biaya, kebijakan toko, kapasitas cabang penerima, atau kelayakan donasi.

## Halaman dan API

| Route | Metode | Keterangan |
| --- | --- | --- |
| `/` | GET | Landing page dan form Quick Demo. |
| `/dashboard` | GET | Ringkasan hasil analisis dataset lokal. |
| `/upload` | GET, POST | Form impor data dan riwayat impor; upload yang valid menjadi dataset aktif. |
| `/export` | GET | Unduh hasil analisis dataset aktif sebagai XLSX. |
| `/products` | GET | Daftar produk dengan pencarian, filter, dan pagination. |
| `/products/<import_id>/<row_number>` | GET | Detail produk, rekomendasi, status, dan riwayat keputusan. |
| `/products/<import_id>/<row_number>/review` | POST | Simpan status serta catatan satu rekomendasi pada batch aktif. |
| `/products/<import_id>/<row_number>/outcome` | POST | Simpan atau perbarui hasil operasional produk pada batch aktif. |
| `/reports?import_id=<id>` | GET | Laporan hasil manual untuk batch terpilih; default batch aktif. |
| `/login`, `/logout` | GET/POST, POST | Masuk dan keluar pada mode autentikasi. Logout memerlukan token CSRF. |
| `/signup` | GET/POST | Mengirim pendaftaran petugas cabang untuk disetujui admin; belum memberi akses data. |
| `/admin`, `/admin/users` | GET, POST | Panel admin dan penyimpanan akun; hanya untuk admin. |
| `/admin/signup/<id>` | POST | Menyetujui atau menolak pendaftaran; hanya untuk admin. |
| `/account` | GET/POST | Melihat akun dan mengganti password sendiri setelah memasukkan password saat ini. |
| `/health` | GET | Respons liveness `{"status":"ok"}`. |
| `/model-monitoring` | GET | Distribusi prediksi per batch dan catatan versi model; mengikuti akses cabang. |
| `/api/predict` | POST | Prediksi satu produk dari JSON berisi delapan fitur model; mengembalikan `waste_proba` dan `risk_level`. |
| `/api/data/critical` | GET | Hingga 50 produk berisiko tinggi. |
| `/api/data/alerts` | GET | Produk yang mendekati kedaluwarsa atau berisiko tinggi. |
| `/api/data/branches` | GET | Ringkasan per cabang. |
| `/api/data/stock_efficiency` | GET | Ringkasan stok dan risiko per kategori. |

Contoh request prediksi:

```json
{
  "Initial_Stock": 100,
  "Sold_Quantity": 60,
  "Remaining_Stock": 40,
  "Expiry_Days_Left": 3,
  "Price": 25000,
  "Discount_Applied": 10,
  "Temperature_(°C)": 27.5,
  "Historical_Avg_Sales": 50
}
```

Contoh bentuk respons (angka dan label bergantung pada hasil model):

```json
{
  "waste_proba": 0.72,
  "risk_level": "High"
}
```

Untuk data dashboard, dataset juga perlu menyediakan identitas dan pengelompokan produk seperti `Product_ID`, `Product_Name`, `Branch`, dan `Category`. Kolom `Waste_Amount` dipakai untuk KPI dan analitik *waste* historis jika tersedia. Dataset contoh berada di `data/raw/dataset_1000.xlsx`.

## Teknologi dan struktur proyek

- **Backend:** Python dan Flask.
- **Data dan ML:** pandas, scikit-learn, XGBoost, joblib, serta SQLite untuk menyimpan hasil impor. Model tersimpan pada `models/wise_model.pkl`.
- **Frontend:** template Jinja, Bootstrap, CSS, dan JavaScript. Grafik batang dashboard dirender oleh template tanpa dependensi grafik eksternal.

```text
app.py                       Route halaman, API, dan pipeline aplikasi
wise_ai/
  config.py                  Path, fitur model, dan ambang risiko
  data_preprocessing.py      Pembacaan Excel dan persiapan fitur
  prediction_engine.py       Prediksi probabilitas dan klasifikasi risiko
  recommendation_system.py  Aturan rekomendasi tindakan
  alert_system.py           Pemilihan produk untuk alert
  dashboard.py              KPI, produk kritis, dan performa cabang
  analytics.py              Ringkasan efisiensi stok per kategori
  import_data.py            Pembacaan dan validasi file upload
  data_store.py             Penyimpanan hasil dan riwayat impor di SQLite
  product_workflow.py       Filter produk dan daftar rekomendasi untuk peninjauan
  outcome_reporting.py      Validasi hasil manual dan agregasi laporan per batch
  model_monitoring.py       Ringkasan distribusi, hash artefak, dan metrik evaluasi
manage_users.py             CLI pembuatan/perubahan akun operasional
run_local_admin.py          Menjalankan server lokal dengan login dan kunci sesi persisten
evaluate_model.py           Evaluasi model pada file berlabel terpisah
serve.py                    Server WSGI Waitress dengan pemeriksaan konfigurasi
web/
  templates/                Template halaman
  static/                   CSS, JavaScript, dan aset gambar
data/raw/                   Dataset input bawaan
instance/                   Database SQLite lokal (dibuat otomatis, diabaikan Git)
models/                     Model ML tersimpan
notebooks/                  Eksplorasi dan pelatihan model
```

## Menjalankan secara lokal

Proyek memerlukan Python 3.10+ dan dependensi runtime pada `requirements.txt`, termasuk `openpyxl` untuk Excel dan `xgboost` untuk memuat model. Dependensi tambahan untuk notebook eksplorasi tersedia di `requirements-dev.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Buka `http://127.0.0.1:5000`. Server lokal menggunakan `127.0.0.1:5000` dan `debug=False` secara default. `WISE_HOST`, `WISE_PORT`, dan `WISE_DEBUG` dapat diatur melalui environment variable saat menjalankan `python app.py`. Lokasi database dapat diatur melalui `WISE_DATABASE_PATH`; default-nya `instance/wise.db`. Contoh untuk development: `$env:WISE_DEBUG = "true"`. Server bawaan Flask tetap ditujukan untuk pengembangan lokal, bukan deployment produksi. Pastikan file dataset dan model tersedia pada path yang ditentukan di `wise_ai/config.py`.

### Login admin di komputer lokal

```powershell
python manage_users.py admin --role admin
python run_local_admin.py
```

Perintah pertama meminta password minimal 12 karakter dua kali. Jika ingin password awal acak, gunakan `python manage_users.py admin --role admin --generate-password`, lalu catat password yang hanya ditampilkan saat dibuat. Buka `http://127.0.0.1:5000/` untuk melihat landing page. Petugas memilih **Sign up**, menentukan password sendiri, lalu menunggu admin menyetujui cabangnya melalui `/admin`. Setelah disetujui, petugas dapat **Sign in**. Admin juga dapat membuat atau memperbarui akun secara langsung dengan username, peran, cabang, dan password awal pilihan admin. Setiap pengguna dapat membuka menu **Akun** untuk mengganti password. `run_local_admin.py` menyimpan kunci sesi dalam `instance/local_session_secret` (diabaikan Git) supaya sesi tidak terputus setiap server restart. Ini hanya untuk `127.0.0.1` melalui HTTP lokal. Jika port 5000 sudah dipakai server demo, hentikan server demo sebelum menjalankan perintah kedua.

### Mode operasional dengan akun

Jalankan perintah berikut di PowerShell setelah memasang `requirements.txt`. `manage_users.py` meminta password melalui terminal sehingga tidak masuk ke riwayat perintah. Password minimal 12 karakter dan disimpan sebagai hash. Nama cabang harus sama persis dengan nilai `Branch` dalam dataset.

```powershell
python manage_users.py admin --role admin
python manage_users.py petugas-jakarta --role branch --branch Jakarta
$env:WISE_AUTH_REQUIRED = "true"
$env:WISE_SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(48))")
$env:WISE_SECURE_COOKIES = "true"
python serve.py
```

Simpan `WISE_SECRET_KEY` di secret manager atau konfigurasi lingkungan yang persisten; nilai harus tetap sama setelah restart agar sesi login tidak terputus. Jangan menaruhnya di repository. `serve.py` menolak berjalan jika autentikasi, kunci sesi persisten, secure cookie, akun, atau konfigurasi tanpa debug belum siap. Secara default Waitress tetap terikat ke `127.0.0.1:5000`; tempatkan reverse proxy HTTPS di depan aplikasi sebelum memberi akses pengguna lain. `WISE_SECURE_COOKIES=true` membuat cookie sesi hanya dikirim browser melalui HTTPS. Endpoint `/health` dapat dipakai sebagai pemeriksaan liveness; log request API dan POST mencatat metode, path, status, dan durasi tanpa isi request.

Mode `python app.py` tetap untuk pengembangan lokal dan, bila `WISE_AUTH_REQUIRED` tidak diatur, tidak memerlukan login. Jangan membuka mode ini ke jaringan publik. Pada mode autentikasi, admin bisa melihat semua cabang dan melakukan impor/ekspor; akun cabang hanya bisa melihat data cabangnya serta mencatat keputusan dan hasil produk pada batch aktif. Periksa hak akses dan data cabang lagi sebelum penggunaan nyata. Database SQLite di `instance/` harus dicadangkan dan dibatasi aksesnya pada sistem operasi.

### Memantau dan mengevaluasi model

Buka `/model-monitoring` untuk melihat maksimal 12 batch terbaru. Halaman ini menampilkan proporsi risiko tinggi, skor rata-rata, dan komposisi label risiko. Import baru menyimpan SHA-256 artefak model; import lama menampilkan “Belum tercatat”. Perbedaan antar batch dapat disebabkan perubahan komposisi produk atau model. Angka ini **bukan metrik akurasi** dan tidak membuktikan bahwa model mengalami *drift* statistik.

Untuk menghitung performa prediksi, sediakan file CSV/XLSX **terpisah dari data pelatihan** dengan kolom upload wajib dan `Waste_Flag` berisi 0 atau 1 untuk setiap baris. File perlu memuat kedua kelas label. Jalankan:

```powershell
python evaluate_model.py data-evaluasi.csv
```

Perintah mencetak JSON berisi jumlah sampel/kelas positif, ROC AUC, average precision, Brier score, precision, recall, F1 pada ambang risiko tinggi 0,7, confusion matrix, dan ringkasan kalibrasi lima rentang. Gunakan `--output hasil-evaluasi.json` jika perlu menyimpan file laporan (tidak menimpa file yang sudah ada), atau `--save-to-db` untuk menambahkan hasil ke riwayat evaluasi di halaman Model; riwayat ini hanya terlihat oleh admin dalam mode autentikasi. CLI menolak file bawaan `data/raw/dataset_1000.xlsx` dan `data/processed/dataset_with_risk_reco.xlsx` sebagai evaluasi independen karena sumber itu terkait notebook pelatihan. `--allow-bundled-smoke-test` hanya untuk memastikan alur perhitungan berjalan dan hasilnya tidak dapat disimpan sebagai riwayat; hasilnya **tidak boleh dilaporkan sebagai performa validasi**. Untuk file lain, aplikasi juga tidak dapat membuktikan bahwa data tersebut benar-benar independen atau representatif; catat sumber, periode, dan definisi label sebelum menafsirkan metrik.

### Mengimpor dan mengekspor data

1. Buka `/upload` dan pilih CSV atau XLSX dengan ukuran maksimal 10 MB dan 10.000 baris.
2. Sediakan kolom `Product_ID`, `Product_Name`, `Branch`, `Category`, dan delapan fitur model yang disebutkan di atas. `Waste_Amount` boleh ditambahkan untuk KPI historis. Kolom tambahan lain dipertahankan dalam hasil.
3. Setelah validasi dan prediksi berhasil, batch tersebut menjadi data aktif untuk dashboard, API data, dan export. Batch sebelumnya tetap tercatat dalam riwayat. Sebelum upload pertama, aplikasi memakai dataset contoh bawaan.
4. Gunakan `/export` untuk mengunduh hasil aktif. Teks yang berpotensi menjadi formula spreadsheet diubah menjadi teks biasa pada file export.

Impor ditolak jika format file, kolom wajib, identitas produk, atau nilai numerik tidak valid. Database lokal perlu dicadangkan jika hasil dan riwayat impor ingin dipertahankan antar mesin.

### Menelusuri dan meninjau produk

1. Buka `/products`, cari ID atau nama, lalu gunakan filter cabang, kategori, dan risiko. Daftar diurutkan dari probabilitas waste tertinggi.
2. Klik nama produk untuk melihat input model, estimasi risiko, dan saran tindakan. Detail dari dataset contoh dapat dibaca, tetapi keputusan hanya dapat disimpan pada batch impor yang aktif.
3. Untuk tiap tindakan, pilih `Disetujui`, `Ditolak`, atau `Ditandai selesai`. Status selesai memerlukan catatan. Perubahan status dan catatan disimpan di SQLite serta ditampilkan dalam riwayat pada halaman detail.

Status tersebut merupakan **catatan manual**. Aplikasi tidak mengubah harga, memindahkan stok, atau mengirim donasi. Batch impor lama tetap dapat dilihat melalui tautan detail yang tersimpan, tetapi keputusannya tidak dapat diubah setelah batch baru menjadi aktif.

### Mencatat dan melihat hasil operasional

1. Pada detail produk dari batch aktif, isi tanggal hasil dan jumlah unit yang terjual, didonasikan, dipindahkan, serta terbuang. Totalnya tidak boleh melebihi `Remaining_Stock` saat impor dan minimal satu unit harus tercatat.
2. Nilai penjualan dan nilai terbuang dalam rupiah bersifat opsional. Kosong berarti belum dilaporkan, bukan nol. Jika mengisi nilai, jumlah unit terkait harus lebih dari nol.
3. Buka `/reports` untuk melihat batch aktif atau pilih batch lama. Laporan hanya menghitung catatan terbaru tiap produk dalam batch terpilih, sehingga perubahan catatan tidak menggandakan total. Riwayat edit tetap ada pada detail produk.

Hasil ini **dilaporkan pengguna** dan belum diverifikasi dari sistem kasir, gudang, atau donasi. Tanggal hasil digunakan untuk tren; tidak ada klaim penurunan waste atau penghematan yang disebabkan WISE AI. Status rekomendasi “ditandai selesai” ditampilkan terpisah dan juga belum diverifikasi.

Untuk menjalankan tes pipeline, validasi, API prediksi, konfigurasi, impor, penelusuran produk, peninjauan, laporan, autentikasi, batas cabang, dan export:

```powershell
python -m unittest discover -s tests -v
```

API prediksi menerima JSON object berisi delapan fitur numerik. Field yang hilang, nilai negatif pada fitur stok/harga/penjualan, diskon di atas 100%, angka tidak finite, dan pecahan pada field jumlah stok atau hari akan ditolak dengan HTTP 400. Pipeline dataset juga memeriksa kolom model, nilai kosong, tipe numerik, dan rentang dasar sebelum menjalankan model.

## Batasan implementasi saat ini

- Dashboard memakai hasil impor terbaru dari SQLite. Sebelum upload pertama, dashboard menghitung hasil dataset Excel bawaan saat request masuk. Belum ada pembaruan otomatis atau sumber data stok langsung; istilah “real-time” pada teks antarmuka belum mencerminkan mekanisme data saat ini.
- Laporan hasil hanya mencakup produk yang diisi manual dalam satu batch. Nilai rupiah dapat kosong dan tidak boleh diartikan sebagai total lengkap seluruh stok.
- Alert tampil di dashboard/API. Belum ada pengiriman notifikasi melalui email, pesan, atau kanal lain.
- Keputusan dan hasil dapat dicatat, tetapi belum ada perubahan harga, pemindahan stok, penyaluran donasi, verifikasi tindakan, atau pengukuran dampak kausal secara otomatis.
- Autentikasi, pembatasan cabang, pengelolaan akun admin, dan ganti password mandiri tersedia dalam mode operasional. Belum ada pemulihan password yang terlupa, audit login persisten, izin lebih rinci, atau integrasi identitas organisasi. Pembatas percobaan login saat ini berada di memori proses.
- Upload dibatasi 10 MB, 10.000 baris, dan untuk XLSX jumlah entri serta ukuran dekompresi; file tetap perlu diperlakukan sebagai data tidak tepercaya. Deployment nyata masih memerlukan reverse proxy HTTPS, backup, monitoring eksternal, serta peninjauan keamanan sesuai lingkungan.
- Dataset contoh memiliki 73 baris dengan `Sold_Quantity` lebih besar daripada `Initial_Stock`; aturan keseimbangan stok belum diterapkan sampai kualitas data sumber dibereskan.
- Model `.pkl` saat ini dapat dimuat, tetapi XGBoost mengeluarkan peringatan kompatibilitas serialisasi. Model sebaiknya diekspor ulang dan diuji dengan versi XGBoost yang dipakai untuk deployment.
- Belum tersedia dataset operasional berlabel yang terbukti independen dari pelatihan. Pemantauan batch menunjukkan distribusi prediksi, sedangkan evaluasi nyata memerlukan label hasil yang benar dan data representatif. Artefak `.pkl` hanya boleh dimuat dari sumber tepercaya.

## Arah pengembangan berikutnya

1. **Integrasi hasil:** sumber transaksi dan stok yang dapat diverifikasi, jejak pelaksana tindakan, serta metode pembanding untuk menilai dampak.
2. **Kesiapan operasional lanjutan:** reset password, audit login persisten, monitoring terpusat, backup terjadwal, dan uji keamanan deployment.
3. **Validasi kualitas model:** kumpulkan data operasional berlabel yang independen, tetapkan periode dan definisi label, lalu jalankan evaluasi berkala dengan ambang penerimaan yang disepakati.

Pengembangan tersebut perlu dilakukan sebelum WISE AI diklaim sebagai sistem monitoring langsung atau sistem pengurangan *food waste* yang telah terukur.
