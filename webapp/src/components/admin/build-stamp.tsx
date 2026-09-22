const buildId = process.env.NEXT_PUBLIC_SURPRIZ_BUILD_ID ?? "development";

export function AdminBuildStamp() {
  return <small className="admin-build-stamp" title={`Сборка ${buildId}`}>Сборка {buildId.slice(0, 16)}</small>;
}
