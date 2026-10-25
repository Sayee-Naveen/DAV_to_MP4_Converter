# DAV to MP4 Converter

An offline, open-source Windows desktop application designed to convert proprietary CCTV/DVR surveillance `.dav` video files (Dahua, Lorex, Amcrest, Uni+, etc.) into standard, universal `.mp4` video files for seamless playback in VLC Media Player and Windows Media Player.

🔗 **GitHub Repository**: [https://github.com/Sayee-Naveen/DAV_to_MP4_Converter](https://github.com/Sayee-Naveen/DAV_to_MP4_Converter)

---

## 🎯 Motivation & Why This Was Built

Surveillance DVR systems (such as Dahua, Lorex, Swann, and Uni+) record security footage in a proprietary container format (`.dav`). These files present several significant challenges for everyday users and investigators:
- **Proprietary Lock-in:** `.dav` files cannot be natively played by standard video players like VLC, Windows Media Player, or web browsers without obscure vendor plugins.
- **Predatory Commercial Utilities:** Most web converters and commercial converter utilities available online charge steep subscription fees, inject intrusive watermarks, or bundle invasive adware and privacy-compromising spyware.
- **Cloud Privacy Risks:** Uploading gigabytes of private home or business surveillance footage to cloud conversion websites creates serious privacy and data security hazards.
- **Broken Timestamps & Anamorphic Distortions:** DVR recordings frequently suffer from missing PTS/DTS timestamps (causing VLC to freeze or drop frames upon seeking) and non-standard anamorphic resolutions (such as 1080N / 960x1080), which appear distorted or squashed as 1:1 squares without proper metadata injection.

**The Solution:** An ultra-fast, 100% offline, privacy-respecting, and free desktop tool that unlocks surveillance footage into high-quality MP4s in seconds using multi-core parallel remuxing and hardware acceleration.

---

## ⚡ Key Highlights & Features

- **⚡ Lightning Remux (100x Speedup):** Leverages stream-copy demuxing to convert 1 GB surveillance files in **2 to 5 seconds** with **zero re-encoding and zero quality loss**.
- **⚙️ Multi-Core Parallel Processing:** Configurable concurrent worker queue (1 to 4 files simultaneously) to fully utilize multi-core / multi-threaded modern CPUs.
- **🚀 GPU Hardware Acceleration:** Built-in support for Intel QuickSync (`h264_qsv`) and Windows MediaFoundation (`h264_mf`) to offload video encoding to the GPU.
- **📐 Anamorphic 1080N Aspect Ratio Correction:** Automatically probes video streams and injects correct display aspect ratios (`DAR 16:9` / `DAR 8:9`) into MP4 containers so footage displays naturally in VLC.
- **🛡️ 100% Offline & Private:** Runs entirely on local hardware. No surveillance footage ever leaves your device.
- **🖱️ Native Drag & Drop:** Drop `.dav` files or entire CCTV folders directly from Windows Explorer into the queue.
- **▶️ Direct VLC Integration:** Detects local VLC installation with one-click **"Play in VLC"** launching and file highlighting in Windows Explorer.
- **🎨 Modern Dark/Light Interface:** Clean, card-based interface built with CustomTkinter and real-time live FFmpeg log inspection.

---

## 🛠️ Installation & Setup

### Prerequisites
- Python 3.10+ (tested on Python 3.14 on Windows 10/11)
- Windows 64-bit

### 1. Clone the Repository
```bash
git clone https://github.com/Sayee-Naveen/DAV_to_MP4_Converter.git
cd DAV_to_MP4_Converter
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Launch the Application
```bash
python main.py
```
Or simply double-click **`Run_DAV_Converter.bat`**.

---

## 📁 Repository Structure

```
DAV_to_MP4_Converter/
├── app_gui.py              # CustomTkinter graphical desktop interface
├── converter_engine.py     # Multi-threaded FFmpeg conversion & probing engine
├── main.py                 # Application entry point
├── Run_DAV_Converter.bat   # Windows one-click batch launcher
├── requirements.txt        # Python package dependencies
├── .gitignore              # Git ignore rules for builds, media, and temp files
├── LICENSE                 # MIT License
└── README.md               # Documentation
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE) - free to use, modify, and distribute.
