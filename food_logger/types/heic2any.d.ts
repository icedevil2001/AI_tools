declare module "heic2any" {
  interface Heic2AnyOptions {
    blob: Blob;
    toType?: string;
    quality?: number;
    multiple?: boolean;
  }
  /** Returns a Blob, or an array of them for multi-image HEIC files. */
  export default function heic2any(options: Heic2AnyOptions): Promise<Blob | Blob[]>;
}
