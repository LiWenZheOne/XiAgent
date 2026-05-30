export interface ZipImageFile {
  name: string;
  bytes: Uint8Array;
}

export function safeAssetImageFileName(value: string): string {
  return (value || "资产图像").replace(/[\\/:*?"<>|]/g, "_").replace(/\s+/g, "_").slice(0, 120);
}

export function extensionFromBlobOrUrl(blob: Blob, url: string): string {
  if (blob.type === "image/png") return ".png";
  if (blob.type === "image/jpeg") return ".jpg";
  if (blob.type === "image/webp") return ".webp";
  const clean = url.split("?")[0] ?? "";
  const match = clean.match(/\.(png|jpe?g|webp|gif)$/i);
  return match ? `.${match[1].toLowerCase().replace("jpeg", "jpg")}` : ".png";
}

export function createStoredZip(files: ZipImageFile[]): Uint8Array {
  const encoder = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const centralChunks: Uint8Array[] = [];
  let offset = 0;
  for (const file of dedupeFileNames(files)) {
    const nameBytes = encoder.encode(file.name);
    const crc = crc32(file.bytes);
    const local = new Uint8Array(30 + nameBytes.length);
    const localView = new DataView(local.buffer);
    localView.setUint32(0, 0x04034b50, true);
    localView.setUint16(4, 20, true);
    localView.setUint16(6, 0, true);
    localView.setUint16(8, 0, true);
    localView.setUint16(10, 0, true);
    localView.setUint16(12, 0, true);
    localView.setUint32(14, crc, true);
    localView.setUint32(18, file.bytes.length, true);
    localView.setUint32(22, file.bytes.length, true);
    localView.setUint16(26, nameBytes.length, true);
    local.set(nameBytes, 30);
    chunks.push(local, file.bytes);

    const central = new Uint8Array(46 + nameBytes.length);
    const centralView = new DataView(central.buffer);
    centralView.setUint32(0, 0x02014b50, true);
    centralView.setUint16(4, 20, true);
    centralView.setUint16(6, 20, true);
    centralView.setUint16(8, 0, true);
    centralView.setUint16(10, 0, true);
    centralView.setUint16(12, 0, true);
    centralView.setUint16(14, 0, true);
    centralView.setUint32(16, crc, true);
    centralView.setUint32(20, file.bytes.length, true);
    centralView.setUint32(24, file.bytes.length, true);
    centralView.setUint16(28, nameBytes.length, true);
    centralView.setUint32(42, offset, true);
    central.set(nameBytes, 46);
    centralChunks.push(central);
    offset += local.length + file.bytes.length;
  }
  const centralOffset = offset;
  const centralSize = centralChunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(8, centralChunks.length, true);
  endView.setUint16(10, centralChunks.length, true);
  endView.setUint32(12, centralSize, true);
  endView.setUint32(16, centralOffset, true);
  return concatBytes([...chunks, ...centralChunks, end]);
}

function dedupeFileNames(files: ZipImageFile[]): ZipImageFile[] {
  const seen = new Map<string, number>();
  return files.map((file) => {
    const count = seen.get(file.name) ?? 0;
    seen.set(file.name, count + 1);
    if (!count) return file;
    const dotIndex = file.name.lastIndexOf(".");
    const base = dotIndex > 0 ? file.name.slice(0, dotIndex) : file.name;
    const ext = dotIndex > 0 ? file.name.slice(dotIndex) : "";
    return { ...file, name: `${base}_${count + 1}${ext}` };
  });
}

function concatBytes(chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }
  return result;
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}
