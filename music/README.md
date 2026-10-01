# Music for Reels

Put tracks here (mp3 or m4a) and point a post file at them with
`"music": "music/<file>"`. The track is baked into the Reel video, so it
plays no matter how the Reel is published.

Only use music you have the right to post: royalty-free or Creative
Commons tracks (e.g. YouTube Audio Library, Pixabay Music, Free Music
Archive), or music you made or licensed. Instagram detects copyrighted
songs and will mute or remove the Reel. If a track's license asks for
credit, put it in `"music_credit"` and it is added to the caption.

Tracks fetched by `music.py` (or a post's `music_search`) land in
`music/<search>/` with `credits.md`, already filtered to licenses that
allow commercial use and editing.
