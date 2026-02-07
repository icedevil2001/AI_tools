#!/bin/env bash

# This script converts a 1080p video to 720p using ffmpeg.
# Usage: ./ffmpeg_1080_to_720p.sh input_video.{mp4,mov} output_video.mp4


input=$1
output=$2

ffmpeg -y -i "$input" \
    -vf "scale=-2:720" \
    -c:v libx264 -crf 28 \
    -preset ultrafast -r 30 \
    -c:a aac -b:a 96k \
    -threads 2 "$output"
