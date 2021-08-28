# tiktok-link

u/tiktok-link is Reddit bot that analyzes TikTok videos with OCR, and replies to the posts with a link to the creator's page. It will soon be live on [r/TikTokCringe](https://reddit.com/r/TikTokCringe).

It uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) to download the video, and [EasyOCR](https://github.com/JaidedAI/EasyOCR) to get the text. It will try to look at the end of the video for the name first, and if it can't find a user that exists, it will look at the beginning of the video for the name that's below the floating logo.

Dependencies are managed with [Poetry](https://python-poetry.org/), because it's the best.

## License

tiktok-link is licensed under the AGPL v3.0. This means that if you fork the bot and run it on Reddit, you have to publish your source code! See [LICENSE](./LICENSE) for details.
