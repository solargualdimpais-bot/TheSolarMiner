export async function isHeicPhoto(file) {
  if (/\.(?:heic|heif)$/i.test(file?.name || "") || /^image\/hei[cf]/i.test(file?.type || "")) return true;
  try {
    const bytes = new Uint8Array(await file.slice(0, 64).arrayBuffer());
    if (String.fromCharCode(...bytes.slice(4, 8)) !== "ftyp") return false;
    const brands = String.fromCharCode(...bytes.slice(8, Math.min(bytes.length, 64)));
    return /heic|heix|hevc|hevx|heis|hevm|hevs|heif|mif1|msf1/i.test(brands);
  } catch {
    return false;
  }
}
