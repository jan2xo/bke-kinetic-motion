#!/usr/bin/env bash
# Render Dock promo - voiceover generation + mix
# Needs: pip install edge-tts ; ffmpeg ; music.wav and RenderDock_Promo_16x9.mp4 in this folder
set -e
VOICE="en-US-ChristopherNeural"   # deep male. Female option: en-US-AriaNeural / en-US-JennyNeural
mkdir -p vo

gen() {  # gen <name> "<text>" <rate>
  python3 -m edge_tts --voice "$VOICE" --rate="$3" --pitch=-6Hz --text "$2" --write-media "vo/$1.mp3"
  # trim leading/trailing silence so each line starts exactly on its beat
  ffmpeg -y -v error -i "vo/$1.mp3" -af "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse" -ar 48000 -ac 2 "vo/$1.wav"
}

gen l1 "Media chaos?"        "+0%"
gen l2 "Meet Render Dock."   "+0%"
gen l3 "Drag."               "+0%"
gen l4 "Organize."           "+0%"
gen l5 "Render."             "+0%"
gen l6 "Production control." "+0%"
gen l7 "Render Dock."        "+0%"
gen l8 "by B K E."           "+10%"

# place lines on their beats (ms), process the voice, duck the music under it, master to -14 LUFS
ffmpeg -y -v error \
 -i vo/l1.wav -i vo/l2.wav -i vo/l3.wav -i vo/l4.wav -i vo/l5.wav -i vo/l6.wav -i vo/l7.wav -i vo/l8.wav -i music.wav \
 -filter_complex "\
[0]adelay=350|350[a0];[1]adelay=2200|2200[a1];[2]adelay=4150|4150[a2];[3]adelay=4800|4800[a3];\
[4]adelay=5500|5500[a4];[5]adelay=6600|6600[a5];\
[6]atempo=1.1,adelay=8520|8520[a6];[7]atempo=1.2,adelay=9170|9170[a7];\
[a0][a1][a2][a3][a4][a5][a6][a7]amix=inputs=8:normalize=0,apad=whole_dur=10,atrim=0:10,\
highpass=f=90,acompressor=threshold=-20dB:ratio=3:attack=5:release=80:makeup=4,\
equalizer=f=3500:t=q:w=1:g=2,volume=1.6[vo];\
[vo]asplit=2[vo1][vosc];\
[8]loudnorm=I=-18:TP=-2,atrim=0:10[mus];\
[mus][vosc]sidechaincompress=threshold=0.03:ratio=5:attack=10:release=250[duck];\
[duck][vo1]amix=inputs=2:normalize=0,alimiter=limit=0.89,loudnorm=I=-14:TP=-1:LRA=11,atrim=0:10[out]" \
 -map "[out]" -ar 48000 mix_vo.wav

# swap the new audio into the video (picture is copied, not re-encoded)
ffmpeg -y -v error -i RenderDock_Promo_16x9.mp4 -i mix_vo.wav -map 0:v -map 1:a \
 -c:v copy -c:a aac -b:a 192k -t 10 -movflags +faststart RenderDock_Promo_16x9_VO.mp4
echo "Done: RenderDock_Promo_16x9_VO.mp4"
