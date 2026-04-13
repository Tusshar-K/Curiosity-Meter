"use client";
import React, { useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Link from "next/link";

export default function FacultyPage() {
  const [method, setMethod] = useState("pdf");
  const [isProcessing, setIsProcessing] = useState(false);
  const [success, setSuccess] = useState(false);
  const [files, setFiles] = useState([]);
  const [url, setUrl] = useState("");

  const handleUpload = async (e) => {
    e.preventDefault();
    if (method === "pdf" && files.length === 0) {
      alert("Please select at least one file first.");
      return;
    }
    if (method === "url" && !url) {
      alert("Please enter a url.");
      return;
    }

    setIsProcessing(true);
    setSuccess(false);

    if (method === "pdf") {
      try {
        // Send files to the standard backend ingestion endpoint
        const uploadPromises = files.map(file => {
          const formData = new FormData();
          formData.append("file", file);
  
          return fetch("http://127.0.0.1:8000/api/v1/ingestion/pdf", {
            method: "POST",
            body: formData,
          }).then(res => res.json());
        });
        await Promise.all(uploadPromises);
        setSuccess(true);
        setFiles([]);
      } catch (error) {
        alert("Failed to upload the file(s).");
      } finally {
        setIsProcessing(false);
      }
    } else {
      // Mock API Call delay for URL
      setTimeout(() => {
        setIsProcessing(false);
        setSuccess(true);
      }, 2000);
    }
  };

  return (
    <div className="min-h-screen p-6 md:p-12 flex flex-col items-center">
      <div className="w-full max-w-4xl flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold">Faculty Portal</h1>
        <Link href="/" className="text-sm text-slate-400 hover:text-white transition-colors">
          ← Back to Home
        </Link>
      </div>

      <Card className="w-full max-w-4xl">
        <div className="mb-6">
          <h2 className="text-xl font-semibold mb-2">Ingest Context Material</h2>
          <p className="text-slate-400 text-sm">Upload course materials to the vector database. Small files go to Postgres, large files &gt;20k tokens will be stored in Qdrant.</p>
        </div>

        <div className="flex gap-4 mb-6 border-b border-slate-700 pb-4">
          <button
            className={`pb-2 px-2 text-sm font-medium transition-all ${method === "pdf" ? "text-blue-400 border-b-2 border-blue-400" : "text-slate-500 hover:text-slate-300"}`}
            onClick={() => setMethod("pdf")}
          >
            PDF Upload
          </button>
          <button
            className={`pb-2 px-2 text-sm font-medium transition-all ${method === "url" ? "text-blue-400 border-b-2 border-blue-400" : "text-slate-500 hover:text-slate-300"}`}
            onClick={() => setMethod("url")}
          >
            URL Import
          </button>
        </div>

        <form onSubmit={handleUpload} className="flex flex-col gap-6">
          {method === "pdf" ? (
            <div className="flex flex-col gap-4">
              <label htmlFor="file-upload" className="border-2 border-dashed border-slate-600 rounded-xl p-12 flex flex-col items-center justify-center text-center hover:border-blue-500 hover:bg-slate-800/30 transition-colors cursor-pointer group">
                <span className="text-4xl mb-4 opacity-50 group-hover:opacity-100 group-hover:text-blue-400 transition-all">📄</span>
                <p className="font-medium mb-1">Click to upload or drag and drop</p>
                <p className="text-xs text-slate-500">PDF documents up to 50MB</p>
                <input id="file-upload" type="file" multiple accept=".pdf" className="hidden" onChange={(e) => setFiles((prev) => [...prev, ...Array.from(e.target.files)])} />
              </label>

              {files.length > 0 && (
                <div className="bg-slate-900 rounded-xl p-4 border border-slate-700">
                  <h4 className="text-sm font-medium text-slate-300 mb-2">Selected Files ({files.length})</h4>
                  <ul className="space-y-2">
                    {files.map((f, i) => (
                      <li key={i} className="flex items-center justify-between text-sm bg-slate-800 p-2 rounded-lg">
                        <span className="text-blue-400 truncate w-3/4">{f.name}</span>
                        <button type="button" onClick={() => setFiles(files.filter((_, idx) => idx !== i))} className="text-slate-500 hover:text-red-400">✕</button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium text-slate-300">Target URL</label>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com/course-syllabus"
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                required
              />
            </div>
          )}

          <div className="flex justify-end mt-4">
            <Button type="submit" disabled={isProcessing}>
              {isProcessing ? "Processing & Embedding..." : "Ingest Material"}
            </Button>
          </div>
        </form>

        {/* Mock success UI */}
        {success && (
          <div className="mt-6 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex flex-col gap-2 animate-in fade-in slide-in-from-bottom-2">
            <div className="flex items-center gap-2 text-emerald-400 font-medium">
              <span>✓</span> Successfully ingested and indexed
            </div>
            <p className="text-sm text-slate-400 ml-6">
              Files are now active in the vector database and ready for query matching.
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}
