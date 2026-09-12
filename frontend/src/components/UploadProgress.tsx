import React from 'react';

type Props = {
  uploadProgress: number | null;
  transcribeProgress: number | null;
};

export default function UploadProgress({ uploadProgress, transcribeProgress }: Props) {
  return (
    <>
      {uploadProgress !== null && (
        <div className="w-full mt-3">
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-[var(--accent)] h-2 rounded-full"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
          <div className="text-xs text-[var(--muted)] mt-1">Uploading: {uploadProgress}%</div>
        </div>
      )}
      {transcribeProgress !== null && (
        <div className="w-full mt-3">
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-green-500 h-2 rounded-full"
              style={{ width: `${transcribeProgress}%` }}
            />
          </div>
          <div className="text-xs text-[var(--muted)] mt-1">
            Transcribing: {transcribeProgress}%
          </div>
        </div>
      )}
    </>
  );
}
