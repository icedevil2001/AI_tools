"use client";

/**
 * Client-side image preparation.
 *
 * Phone cameras produce 3-5MB files. Uploading those raw makes the log slow
 * over mobile data and costs far more in vision tokens than it buys in
 * accuracy, so everything is resized before it leaves the device. This mirrors
 * the max-edge-1024 approach in poster_summary/poster_summary.py.
 */

const MAX_EDGE = 1024;
const JPEG_QUALITY = 0.82;

/**
 * iPhones shoot HEIC by default. A file picked from the photo library (rather
 * than taken with `capture`) will often arrive as HEIC, which no browser canvas
 * can decode, so it is converted first.
 */
async function toDecodableBlob(file: File): Promise<Blob> {
  const isHeic =
    /image\/hei[cf]/i.test(file.type) || /\.(heic|heif)$/i.test(file.name);

  if (!isHeic) return file;

  // Imported lazily so the ~1MB decoder only downloads for users who actually
  // pick a HEIC file.
  const heic2any = (await import("heic2any")).default;
  const converted = await heic2any({ blob: file, toType: "image/jpeg", quality: JPEG_QUALITY });
  return Array.isArray(converted) ? converted[0] : converted;
}

async function loadImage(blob: Blob): Promise<{ width: number; height: number; source: CanvasImageSource }> {
  // createImageBitmap applies EXIF orientation, so photos taken sideways are
  // not sent to the model upside down.
  if (typeof createImageBitmap === "function") {
    try {
      const bitmap = await createImageBitmap(blob, { imageOrientation: "from-image" });
      return { width: bitmap.width, height: bitmap.height, source: bitmap };
    } catch {
      // Fall through to the <img> path below.
    }
  }

  const url = URL.createObjectURL(blob);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = () => reject(new Error("Could not decode that image."));
      el.src = url;
    });
    return { width: img.naturalWidth, height: img.naturalHeight, source: img };
  } finally {
    URL.revokeObjectURL(url);
  }
}

export interface PreparedImage {
  /** `data:image/jpeg;base64,...`, for the vision request. */
  dataUrl: string;
  /** The same bytes as a blob, for upload to Supabase Storage. */
  blob: Blob;
  width: number;
  height: number;
}

/**
 * Decode, orient, downscale and re-encode a photo as JPEG.
 *
 * Throws a user-presentable Error if the file cannot be decoded. Callers should
 * let the person continue logging manually rather than blocking on this.
 */
export async function prepareImage(file: File): Promise<PreparedImage> {
  const decodable = await toDecodableBlob(file);
  const { width, height, source } = await loadImage(decodable);

  if (!width || !height) {
    throw new Error("Could not read that image.");
  }

  const scale = Math.min(1, MAX_EDGE / Math.max(width, height));
  const targetWidth = Math.max(1, Math.round(width * scale));
  const targetHeight = Math.max(1, Math.round(height * scale));

  const canvas = document.createElement("canvas");
  canvas.width = targetWidth;
  canvas.height = targetHeight;

  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Could not process that image on this device.");
  ctx.drawImage(source, 0, 0, targetWidth, targetHeight);

  if ("close" in source && typeof source.close === "function") {
    source.close();
  }

  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
  );
  if (!blob) throw new Error("Could not process that image on this device.");

  const dataUrl = canvas.toDataURL("image/jpeg", JPEG_QUALITY);

  return { dataUrl, blob, width: targetWidth, height: targetHeight };
}
