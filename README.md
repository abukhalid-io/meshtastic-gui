# Meshtastic GUI

Aplikasi desktop (Windows & Linux) untuk konek dan setting perangkat [Meshtastic](https://meshtastic.org/docs/introduction/) — tanpa command line. Dibuat dengan Python + PySide6 (Qt), memakai library resmi [`meshtastic`](https://pypi.org/project/meshtastic/). Menu dan fiturnya mengikuti struktur app Android resminya (Nodes, Pesan/Conversations, Peta, Settings per-kategori).

## Fitur

- **Koneksi**: USB (serial) atau TCP/IP (WiFi).
- **Dashboard**: info perangkat (firmware, hardware model, node ID).
- **Nodes**: daftar node di mesh — cari, urutkan, dan klik-kanan untuk favorit, abaikan, trace route, minta posisi, kirim DM, atau hapus node.
- **Pesan**: broadcast per channel (0-7) atau direct message ke node tertentu.
- **Peta**: plot posisi GPS node secara offline (relatif, bukan citra satelit — tidak butuh internet).
- **Channels**: lihat channel aktif, import/export via URL.
- **Pengaturan**: menu kategori seperti app Android — User, Device, LoRa, Position, Power, Network, Display, Bluetooth, Security, plus semua module config (MQTT, Serial, dll) — dibuat otomatis dari skema protobuf perangkat yang terpasang, jadi selalu sinkron dengan versi firmware/library.
- **Log**: event mentah untuk debugging.

Semua I/O ke perangkat berjalan di thread terpisah, jadi UI tidak freeze.

## Install & jalankan

### Windows

```bash
run_windows.bat
```

### Linux

```bash
chmod +x run_linux.sh
./run_linux.sh
```

Di Linux, masukkan user ke grup `dialout` (atau `uucp` di beberapa distro) supaya bisa akses port serial tanpa `sudo`:

```bash
sudo usermod -aG dialout $USER
# lalu logout/login ulang
```

### Install langsung dari GitHub (Windows/Linux/macOS)

Butuh Python 3.9+ dan `pip`. Disarankan pakai [pipx](https://pipx.pypa.io/) supaya terisolasi:

```bash
pipx install "git+https://github.com/abukhalid-io/meshtastic-gui.git"
meshtastic-gui
```

Atau dengan `pip` biasa (sebaiknya di virtual environment):

```bash
pip install "git+https://github.com/abukhalid-io/meshtastic-gui.git"
meshtastic-gui
```

### Dari source (clone manual)

```bash
git clone https://github.com/abukhalid-io/meshtastic-gui.git
cd meshtastic-gui
pip install -e .
meshtastic-gui
```

## Cara pakai singkat

1. Colok perangkat Meshtastic ke laptop via USB.
2. Buka aplikasi, pilih mode **Serial (USB)**, klik **Refresh** kalau port belum muncul, pilih portnya (`COM3`/`COM4`/... di Windows, `/dev/ttyUSB0`/`/dev/ttyACM0` di Linux).
3. Klik **Connect**. Tunggu beberapa detik sampai status "Terhubung".
4. Tab **Nodes** mulai terisi begitu perangkat mendengar node lain di mesh (offline, via LoRa — tidak butuh internet).
5. Tab **Pesan** untuk chat; tab **Peta** untuk lihat posisi node; tab **Pengaturan** untuk konfigurasi radio lengkap.

Untuk konek via WiFi, pilih mode **TCP/IP (WiFi)** dan isi IP node-nya (atau coba hostname `meshtastic.local`).

> Mesh Meshtastic sendiri berjalan **offline** lewat radio LoRa — tidak butuh internet sama sekali. "Online" di sini cuma cara aplikasi nyambung ke satu node (USB vs WiFi/TCP).

## Struktur proyek

```
meshtastic-gui/
  main.py                   # jalanin dari source: python main.py
  pyproject.toml            # packaging (pip install / entry point `meshtastic-gui`)
  meshtastic_gui/
    app.py                  # bootstrap Qt app (dipakai main.py & entry point)
    bridge.py               # jembatan thread-safe ke library meshtastic (pubsub -> Qt signal)
    main_window.py           # window utama + wiring semua tab
    proto_form.py            # generator form dinamis dari protobuf config (Settings)
    theme.py                 # palet warna & stylesheet ala Meshtastic
    icon.py                  # ikon app (mesh/node, digambar langsung, tanpa aset eksternal)
    utils.py
    tabs/
      dashboard_tab.py
      nodes_tab.py
      messages_tab.py
      channels_tab.py
      settings_tab.py
      map_tab.py
      log_tab.py
  run_windows.bat
  run_linux.sh
```

## Troubleshooting

- **Port serial tidak muncul**: pastikan driver USB-to-serial terinstall (chip umum: CP2102, CH340/CH9102, atau native USB Espressif). Cek Device Manager (Windows) / `dmesg` (Linux) untuk error driver.
- **"Timed out waiting for connection completion"**: port kebuka tapi device tidak membalas protokol Meshtastic sama sekali — biasanya device belum boot ke firmware app (nyangkut di bootloader) atau perlu reset manual. Coba cabut-colok USB atau tekan tombol RESET fisik di board, lalu Connect lagi.
- **Tombol Pengaturan gagal ("Gagal ..." dialog)**: kemungkinan versi firmware memakai field protobuf berbeda dari versi `meshtastic` python yang terpasang — cek tab **Log**, dan pastikan `pip install -U meshtastic` ke versi terbaru yang cocok dengan firmware.

## Catatan

Ini proyek independen/tidak resmi, dibangun di atas library Python resmi [`meshtastic`](https://github.com/meshtastic/python). Bukan produk resmi tim Meshtastic — ada juga [Meshtastic Desktop App resmi](https://meshtastic.org/docs/software/android/user/desktop/) (Kotlin Multiplatform, `.msi`/`.deb`/`.AppImage`/`.dmg`) kalau butuh parity penuh dengan app Android/iOS mereka.
