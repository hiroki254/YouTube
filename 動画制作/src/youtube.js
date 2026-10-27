const ID_PATTERN = /^[A-Za-z0-9_-]{11}$/;

// youtu.be / watch?v= / shorts / live / embed の URL から動画IDを取り出し、正規の URL にそろえる
export function parseYouTubeUrl(input) {
  let url;
  try {
    url = new URL(input);
  } catch {
    throw new Error(`URL として読めません: ${input}`);
  }
  const host = url.hostname.replace(/^(www\.|m\.|music\.)/, '');
  let id = null;
  if (host === 'youtu.be') {
    id = url.pathname.split('/')[1];
  } else if (host === 'youtube.com') {
    if (url.pathname === '/watch') id = url.searchParams.get('v');
    else {
      const [, kind, value] = url.pathname.split('/');
      if (['shorts', 'live', 'embed'].includes(kind)) id = value;
    }
  }
  if (!id || !ID_PATTERN.test(id)) {
    throw new Error(`YouTube の動画 URL ではありません: ${input}`);
  }
  return { id, url: `https://www.youtube.com/watch?v=${id}` };
}
