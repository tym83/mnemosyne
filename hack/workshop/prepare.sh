#!/bin/sh
# Runs inside a studio pod: tools, Python packages, NotaGen and its weights.
set -e
apt-get update -qq
apt-get install -y -qq lilypond fluidsynth fluid-soundfont-gm abcmidi git >/dev/null
python -m venv /work/venv
. /work/venv/bin/activate
pip install -q --upgrade pip
pip install -q torch --index-url https://download.pytorch.org/whl/cpu
pip install -q transformers==4.40.0 abctoolkit==0.0.6 samplings==0.1.7 pyparsing==3.2.1 music21 numpy pyyaml ortools ezdxf huggingface_hub
[ -d /work/NotaGen ] || git clone -q https://github.com/ElectricAlexis/NotaGen /work/NotaGen
cd /work/NotaGen/gradio
# Upstream gives up on a piece after 10 minutes (sized for a GPU) and has a
# typo on the streaming path; on CPU a piece takes hours.
sed -i 's/time.time() - start_time > 10 \* 60/time.time() - start_time > int(os.environ.get("NOTAGEN_TIMEOUT", "43200"))/; s/context_tunebody_lines\[-cut_index:\]/context_tunebody_liness[-cut_index:]/' inference.py
grep -q '^import os' inference.py || sed -i '1i import os' inference.py
[ -f weights_notagenx_p_size_16_p_length_1024_p_layers_20_h_size_1280.pth ] || \
  python -c "from huggingface_hub import hf_hub_download as d; d('ElectricAlexis/NotaGen', 'weights_notagenx_p_size_16_p_length_1024_p_layers_20_h_size_1280.pth', local_dir='.')"
echo ready
