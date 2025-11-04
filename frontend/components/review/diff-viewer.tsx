"use client";

import { useEffect, useState } from "react";
import { Diff, Hunk, parseDiff } from "react-diff-view";
import type { DiffResponse, DiffFile } from "@/lib/types";
import { fetchRepoDiff } from "@/lib/api";
import { getCachedDiff, setCachedDiff, clearDiffCache } from "@/lib/diff-cache";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { RefreshCw } from "lucide-react";
import "react-diff-view/style/index.css";

type DiffViewerProps = {
  repoId: string;
  seedSha: string;
  headBranch?: string;
  accessToken?: string;
  onError?: (error: Error) => void;
};

export function DiffViewer({ repoId, seedSha, headBranch = "main", accessToken, onError }: DiffViewerProps) {
  const [diffData, setDiffData] = useState<DiffResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadDiff() {
      if (!accessToken) {
        setError("Authentication required");
        setLoading(false);
        return;
      }

      const cached = getCachedDiff(repoId, headBranch);
      if (cached) {
        setDiffData(cached);
        setLoading(false);
        setError(null);
        if (cached.files.length > 0 && !selectedFile) {
          setSelectedFile(cached.files[0].filename);
        }
        return;
      }

      setLoading(true);
      setError(null);
      try {
        const data = await fetchRepoDiff(repoId, headBranch, { accessToken });
        if (!cancelled) {
          setDiffData(data);
          setCachedDiff(repoId, headBranch, data);
          if (data.files.length > 0 && !selectedFile) {
            setSelectedFile(data.files[0].filename);
          }
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Failed to load diff";
          setError(message);
          if (onError && err instanceof Error) {
            onError(err);
          }
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadDiff();

    return () => {
      cancelled = true;
    };
  }, [repoId, headBranch, accessToken, onError, selectedFile]);

  const handleRefresh = async () => {
    if (!accessToken || isRefreshing) return;

    setIsRefreshing(true);
    clearDiffCache(repoId, headBranch);
    setError(null);

    try {
      const data = await fetchRepoDiff(repoId, headBranch, { accessToken });
      setDiffData(data);
      setCachedDiff(repoId, headBranch, data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to refresh diff";
      setError(message);
      if (onError && err instanceof Error) {
        onError(err);
      }
    } finally {
      setIsRefreshing(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-zinc-500">
          Loading diff...
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-8">
          <p className="text-sm text-red-600">Error: {error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!diffData || diffData.files.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-zinc-500">
          No changes found. The candidate repository matches the seed repository.
        </CardContent>
      </Card>
    );
  }

  const currentFile = diffData.files.find((f) => f.filename === selectedFile) || diffData.files[0];

  let parsedFiles: any[] = [];
  if (currentFile.patch) {
    try {
      let patchText = currentFile.patch;

      if (!patchText.startsWith("diff --git") && !patchText.startsWith("---")) {
        const oldPath = currentFile.previousFilename || currentFile.filename;
        const newPath = currentFile.filename;
        patchText = `diff --git a/${oldPath} b/${newPath}\n${patchText}`;
      }

      if (!patchText.includes("\n--- ") && !patchText.includes("\n+++ ")) {
        const oldPath = currentFile.previousFilename || `/dev/null`;
        const newPath = currentFile.filename;
        patchText = `diff --git a/${oldPath} b/${newPath}
--- a/${oldPath}
+++ b/${newPath}
${patchText}`;
      }

      const parsed = parseDiff(patchText);
      parsedFiles = Array.isArray(parsed) ? parsed : [parsed];
    } catch (err) {
      console.error("Failed to parse diff:", err, {
        patch: currentFile.patch?.substring(0, 200),
        filename: currentFile.filename,
      });
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4 text-sm text-zinc-600">
          <span>
            <span className="font-medium text-green-600">+{diffData.totalAdditions}</span>
            {" / "}
            <span className="font-medium text-red-600">-{diffData.totalDeletions}</span>
            {" in "}
            <span className="font-medium">{diffData.files.length}</span> file{diffData.files.length !== 1 ? "s" : ""}
          </span>
          <span className="text-zinc-400">•</span>
          <span>
            {diffData.commits.length} commit{diffData.commits.length !== 1 ? "s" : ""}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isRefreshing || !accessToken}
            title="Refresh diff data"
          >
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
          </Button>
          {diffData.htmlUrl && (
            <Button variant="outline" size="sm" asChild>
              <Link href={diffData.htmlUrl} target="_blank" rel="noopener noreferrer">
                View on GitHub
              </Link>
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Files</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="max-h-[600px] overflow-y-auto">
              {diffData.files.map((file) => (
                <button
                  key={file.filename}
                  onClick={() => setSelectedFile(file.filename)}
                  className={`w-full px-4 py-2 text-left text-sm hover:bg-zinc-50 ${
                    selectedFile === file.filename ? "bg-zinc-100 font-medium" : ""
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="truncate">{file.filename}</span>
                    <div className="ml-2 flex items-center gap-1">
                      {file.status === "added" && (
                        <Badge className="bg-green-50 text-green-700 border-green-200">
                          +{file.additions}
                        </Badge>
                      )}
                      {file.status === "removed" && (
                        <Badge className="bg-red-50 text-red-700 border-red-200">
                          -{file.deletions}
                        </Badge>
                      )}
                      {(file.status === "modified" || file.status === "renamed") && (
                        <>
                          <Badge className="bg-green-50 text-green-700 border-green-200">
                            +{file.additions}
                          </Badge>
                          <Badge className="bg-red-50 text-red-700 border-red-200">
                            -{file.deletions}
                          </Badge>
                        </>
                      )}
                    </div>
                  </div>
                  {file.previousFilename && (
                    <div className="mt-1 text-xs text-zinc-500 truncate">
                      from {file.previousFilename}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{currentFile.filename}</CardTitle>
            {currentFile.previousFilename && (
              <CardDescription className="text-xs">
                Renamed from {currentFile.previousFilename}
              </CardDescription>
            )}
          </CardHeader>
          <CardContent className="p-0">
            <div className="max-h-[600px] overflow-auto">
              {parsedFiles.length > 0 ? (
                parsedFiles.map((file, idx) => {
                  if (!file || !file.hunks || !Array.isArray(file.hunks)) {
                    return (
                      <div key={idx} className="p-4 text-sm text-red-600">
                        <p>Error: Invalid diff format</p>
                        {currentFile.patch && (
                          <pre className="mt-2 whitespace-pre-wrap text-xs">
                            {currentFile.patch.substring(0, 500)}
                          </pre>
                        )}
                      </div>
                    );
                  }
                  return (
                    <Diff key={idx} viewType="unified" diffType={file.type || "modified"} hunks={file.hunks}>
                      {(hunks: any[]) =>
                        hunks && Array.isArray(hunks) ? (
                          hunks.map((hunk: any, hunkIdx: number) => (
                            <Hunk key={hunkIdx} hunk={hunk} />
                          ))
                        ) : (
                          <div className="p-4 text-sm text-zinc-600">No hunks available</div>
                        )
                      }
                    </Diff>
                  );
                })
              ) : currentFile.patch ? (
                <div className="p-4">
                  <pre className="whitespace-pre-wrap text-xs font-mono text-zinc-700 bg-zinc-50 p-4 rounded border">
                    {currentFile.patch}
                  </pre>
                  {currentFile.blobUrl && (
                    <Button variant="outline" size="sm" className="mt-4" asChild>
                      <Link href={currentFile.blobUrl} target="_blank" rel="noopener noreferrer">
                        View file on GitHub
                      </Link>
                    </Button>
                  )}
                </div>
              ) : currentFile.status === "added" ? (
                <div className="p-4 text-sm text-zinc-600">
                  <p className="font-medium text-green-600">New file</p>
                  <p className="mt-2">This file was added. {currentFile.additions} lines added.</p>
                  {currentFile.blobUrl && (
                    <Button variant="outline" size="sm" className="mt-4" asChild>
                      <Link href={currentFile.blobUrl} target="_blank" rel="noopener noreferrer">
                        View file on GitHub
                      </Link>
                    </Button>
                  )}
                </div>
              ) : currentFile.status === "removed" ? (
                <div className="p-4 text-sm text-zinc-600">
                  <p className="font-medium text-red-600">Deleted file</p>
                  <p className="mt-2">This file was removed. {currentFile.deletions} lines deleted.</p>
                </div>
              ) : (
                <div className="p-4 text-sm text-zinc-600">
                  <p>Diff content unavailable. {currentFile.additions} additions, {currentFile.deletions} deletions.</p>
                  {currentFile.blobUrl && (
                    <Button variant="outline" size="sm" className="mt-4" asChild>
                      <Link href={currentFile.blobUrl} target="_blank" rel="noopener noreferrer">
                        View file on GitHub
                      </Link>
                    </Button>
                  )}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {diffData.commits.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Commits</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {diffData.commits.map((commit) => (
                <div key={commit.sha} className="rounded border border-zinc-200 bg-white p-3 text-sm">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="font-medium text-zinc-900">{commit.message}</p>
                      <p className="mt-1 text-xs text-zinc-500">
                        {commit.author} • {new Date(commit.date).toLocaleString()}
                      </p>
                    </div>
                    <code className="ml-4 rounded bg-zinc-100 px-2 py-1 text-xs text-zinc-600">
                      {commit.sha}
                    </code>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

