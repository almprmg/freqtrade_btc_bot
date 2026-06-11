# 🚀 GPU Machine — أسهل طريقة (3 أوامر فقط)

> **الهدف:** انقل المشروع لجهاز GPU، خلّي Claude يكمل من حيث توقّفنا.

## ⚡ Quick Start (3 أوامر)

### على الجهاز الجديد (Windows + GPU):

```powershell
# 1. افتح PowerShell (Win → اكتب PowerShell → Enter)

# 2. انسخ الـrepo
git clone https://github.com/almprmg/freqtrade_btc_bot.git
cd freqtrade_btc_bot

# 3. شغّل AUTO_START — يُثبّت كل شيء تلقائيًا
powershell -ExecutionPolicy Bypass -File GPU_HANDOFF\AUTO_START.ps1
```

**سيُنفّذ AUTO_START تلقائيًا:**
1. ✅ يثبّت Git + Python + Node.js (لو ناقصة)
2. ✅ يتحقّق من GPU
3. ✅ ينشئ Python venv + يثبّت PyTorch CUDA + ML stack
4. ✅ يثبّت Claude Code
5. ✅ ينسخ **15 Skill** + **8 ذاكرة** إلى `~/.claude/`
6. ✅ ينشئ `CLAUDE.md` يخبر الـAI الجديد بكل السياق

**المدّة:** ~20 دقيقة

---

## 📦 نقل البيانات (يدوي بـUSB - الأسهل)

> **مهم:** بعد ما AUTO_START يكمل، تحتاج تنقل البيانات.

### من الجهاز القديم (CPU)، انسخ على USB:

| المجلد | الحجم تقريبي |
|---|---|
| `D:\pythone\freqtrade_btc_bot\user_data\data\` | ~500MB |
| `D:\pythone\freqtrade_btc_bot\research\experiments\` | ~200MB (اختياري) |
| `C:\Users\user\.claude\projects\d--pythone-trad-system\*.jsonl` | ~50MB (محادثات Claude) |

### الصق في الجهاز الجديد:

| من USB | إلى |
|---|---|
| `user_data\data\` | `D:\projects\freqtrade_btc_bot\user_data\data\` |
| `research\experiments\` | `D:\projects\freqtrade_btc_bot\research\experiments\` |
| `*.jsonl` | `C:\Users\<اسمك>\.claude\projects\d--pythone-trad-system\` |

---

## 🤖 شغّل Claude

```powershell
# سجّل دخول (مرة وحدة):
claude login

# افتح المشروع:
cd D:\projects\freqtrade_btc_bot
claude
```

**Claude الجديد سيرى:**
- ✅ كل محادثاتنا السابقة (من `.jsonl`)
- ✅ كل الـ8 ذاكرات (postgres-zombie-txns، deploy-topology، إلخ)
- ✅ كل الـ15 skill (strategy-architect، bot-builder، إلخ)
- ✅ `CLAUDE.md` يخبره بالسياق
- ✅ `GPU_HANDOFF/CONTEXT_FOR_GPU_AI.md` يلخّص كل ما عملناه

**ببساطة قل له:**
> "ابدأ بتدريب LSTM على BTC"

وسيُنفّذ تلقائيًا:
```powershell
python GPU_HANDOFF\dl_train_lstm.py --coin BTC --epochs 50
```

النتيجة المتوقّعة:
- Validation correlation ≥ +0.15 (KNN baseline +0.06)
- ~30 دقيقة على RTX 3060/12GB

---

## 📚 ماذا يحتوي مجلد `GPU_HANDOFF/`

| الملف | الوصف |
|---|---|
| `AUTO_START.ps1` | ⭐ شغّله أولاً — يثبّت كل شيء |
| `setup_gpu.ps1` | تثبيت Python venv + PyTorch CUDA فقط |
| `sync_data.ps1` | نقل تلقائي بـSCP (لو عندك SSH) |
| `dl_train_lstm.py` | LSTM training جاهز |
| `CONTEXT_FOR_GPU_AI.md` | ملخّص ما عمله Claude للـAI الجديد |
| `skills/` | الـ15 skill (bot-builder, strategy-architect, إلخ) |
| `memory/` | الـ8 ذاكرات (deploy-topology، postgres-zombie، إلخ) |

---

## 🆘 لو علقت

| المشكلة | الحل |
|---|---|
| `winget not found` | ثبّت "App Installer" من Microsoft Store |
| `nvidia-smi not found` | ثبّت NVIDIA driver من nvidia.com |
| `torch.cuda.is_available() == False` | السائق قديم، حدّثه |
| `git not recognized` | أعد فتح PowerShell بعد تثبيت Git |
| Out of memory أثناء التدريب | قلّل `--batch 64` بدل 256 |

---

## 🎯 خطوات Claude التلقائية بعد البدء

عندما تقول لـClaude "ابدأ"، سيقوم بـ:

1. **يقرأ** `CLAUDE.md` + `CONTEXT_FOR_GPU_AI.md` + `MEMORY.md`
2. **يتحقّق** من الـGPU + البيانات
3. **يبدأ** تدريب LSTM على BTC
4. **يقارن** النتيجة بـKNN baseline (+0.06)
5. **إذا نجح** (corr ≥ +0.15) → يكرّر على ETH/SOL/BNB/ADA/XRP/DOGE
6. **يبني** strategy جديدة `BtcAnalogV3Strategy` تستخدم LSTM
7. **يختبر** 9 سنوات backtest
8. **يقدّم** report مقارن (LSTM vs KNN)
9. **commit + push** كل التقدّم على GitHub
