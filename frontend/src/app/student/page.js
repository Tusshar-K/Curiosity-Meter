"use client";
import React, { useState, useEffect } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Link from "next/link";

export default function StudentPage() {
  const [question, setQuestion] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [streamLog, setStreamLog] = useState([]);
  const [finalResult, setFinalResult] = useState(null);
  const [documents, setDocuments] = useState([]);

  useEffect(() => {
    let isMounted = true;
    
    const fetchDocs = async (retries = 5, delay = 2000) => {
      try {
        const res = await fetch("http://127.0.0.1:8000/api/v1/ingestion/files");
        if (!res.ok) throw new Error("Failed to connect to backend");
        
        const data = await res.json();
        if (isMounted && data.files) setDocuments(data.files);
      } catch (e) {
        if (retries > 0) {
          console.warn(`Backend not ready yet, retrying in ${delay / 1000}s... (${retries} retries left)`);
          setTimeout(() => {
            if (isMounted) fetchDocs(retries - 1, delay * 1.5);
          }, delay);
        } else {
          console.error("Failed to load topic legend after retries", e);
        }
      }
    };
    
    fetchDocs();

    return () => {
      isMounted = false;
    };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;

    setIsSubmitting(true);
    setStreamLog([]);
    setFinalResult(null);

    try {
      const response = await fetch("http://127.0.0.1:8000/api/v1/assessment/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: "sess_942x2",
          student_id: "student_123",
          question_text: question
        }),
      });

      if (!response.ok) throw new Error("Failed to connect to assessment stream");

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");

      let buffer = "";
      let currentEvent = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop(); // keep the last incomplete line

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i];
          if (line.startsWith("event: ")) {
            currentEvent = line.substring(7).trim();
          } else if (line.startsWith("data: ")) {
            const dataStr = line.substring(6).trim();
            if (dataStr) {
               try {
                  const data = JSON.parse(dataStr);
                  if (currentEvent === "status") {
                    setStreamLog((prev) => [...prev, data.message]);
                  } else if (currentEvent === "result") {
                    setFinalResult(data);
                  }
               } catch (err) {
                  // Ignore JSON parse errors for incomplete blocks during streaming
               }
            }
          }
        }
      }
    } catch (err) {
      setStreamLog((prev) => [...prev, "Error: " + err.message]);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen p-6 md:p-12 max-w-7xl mx-auto flex flex-col gap-8">

      {/* Header */}
      <div className="w-full flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-purple-400 to-pink-500">Live Assessment</h1>
          <p className="text-slate-400 mt-1">Session ID: sess_942x2</p>
        </div>
        <Link href="/" className="text-sm text-slate-400 hover:text-white transition-colors">
          ← Back to Dashboard
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

        {/* Left Col: Legend/Flags */}
        <div className="lg:col-span-1 space-y-6">
          <Card className="border-l-4 border-l-purple-500">
            <h3 className="text-lg font-semibold mb-4 text-purple-100">Topic Legend</h3>
            <p className="text-sm text-slate-400 mb-4">
              Your question should draw concepts actively from the provided context materials:
            </p>
            <ul className="space-y-3">
              {documents.length > 0 ? (
                documents.map((doc) => (
                  <li key={doc.id} className="flex items-start gap-2 bg-slate-800/50 p-2 rounded-lg border border-slate-700">
                    <span className="text-xl">📄</span>
                    <div className="flex-1 overflow-hidden">
                      <p className="text-sm font-medium text-slate-200 truncate" title={doc.source_name}>{doc.source_name}</p>
                      <p className="text-xs text-slate-500">Ingested material</p>
                    </div>
                  </li>
                ))
              ) : (
                <li className="text-sm text-slate-500 italic">No source materials discovered.</li>
              )}
            </ul>
          </Card>
        </div>

        {/* Right Col: Assessment Area */}
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <label className="text-lg font-medium text-slate-200">What is your question?</label>
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Type your question here. Try to aim for higher-level Bloom's taxonomy (e.g. Synthesis or Evaluation) rather than simple recall..."
                className="w-full bg-slate-900 border border-slate-700 rounded-xl p-4 min-h-[150px] outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all resize-y text-slate-100"
                required
                disabled={isSubmitting}
              />
              <div className="flex justify-between items-center mt-2">
                <span className="text-xs text-slate-500">Supports markdown formatting</span>
                <Button type="submit" disabled={isSubmitting} className="bg-purple-600 hover:bg-purple-500 hover:shadow-purple-500/25">
                  {isSubmitting ? "Submitting..." : "Submit Question"}
                </Button>
              </div>
            </form>
          </Card>

          {/* SSE Stream Logs */}
          {(streamLog.length > 0 || isSubmitting) && (
            <Card className="bg-[#0a0f1c] border-slate-800 font-mono text-sm shadow-inner">
              <h4 className="text-slate-500 mb-4 pb-2 border-b border-slate-800 tracking-wider">SYSTEM LOGS</h4>
              <ul className="space-y-2">
                {streamLog.map((log, idx) => (
                  <li key={idx} className="flex items-center gap-3 text-slate-300 animate-in fade-in slide-in-from-left-2">
                    <span className="text-blue-400">[{new Date().toLocaleTimeString()}]</span>
                    {log}
                  </li>
                ))}
                {isSubmitting && (
                  <li className="flex items-center gap-3 text-slate-500 animate-pulse mt-2">
                    <span className="text-blue-400/50">[{new Date().toLocaleTimeString()}]</span>
                    Waiting for output...
                  </li>
                )}
              </ul>
            </Card>
          )}

          {/* Final Result Board */}
          {finalResult && (
            <Card className="border border-emerald-500/30 bg-emerald-900/10 animate-in slide-in-from-bottom-4 fade-in duration-500 relative overflow-hidden">
              <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500"></div>

              <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                <div>
                  <h3 className="text-2xl font-bold tracking-tight text-white">Assessment Complete</h3>
                  <p className="text-emerald-400/80 mt-1">Evaluation successfully generated.</p>
                </div>
                <div className="bg-emerald-950/50 border border-emerald-800 px-6 py-3 rounded-xl flex items-center justify-center text-center shadow-[0_0_15px_rgba(16,185,129,0.15)]">
                  <div>
                    <span className="block text-xs uppercase tracking-wider text-emerald-500 mb-1">Total Score</span>
                    <span className="text-3xl font-black text-emerald-400">{finalResult.score} <span className="text-lg font-normal text-emerald-800">/ 10.0</span></span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
                <div className="bg-slate-900/50 p-3 rounded-lg border border-slate-800">
                  <span className="block text-xs text-slate-500 mb-1">Bloom Level</span>
                  <span className="font-semibold text-slate-200">{finalResult.bloom} / 6</span>
                </div>
                <div className="bg-slate-900/50 p-3 rounded-lg border border-slate-800">
                  <span className="block text-xs text-slate-500 mb-1">Depth</span>
                  <span className="font-semibold text-slate-200">{finalResult.depth} / 4</span>
                </div>
                <div className="bg-slate-900/50 p-3 rounded-lg border border-slate-800">
                  <span className="block text-xs text-slate-500 mb-1">Relevance</span>
                  <span className="font-semibold text-slate-200">{finalResult.relevance}</span>
                </div>
                <div className="bg-slate-900/50 p-3 rounded-lg border border-slate-800">
                  <span className="block text-xs text-slate-500 mb-1">Penalty</span>
                  <span className="font-semibold text-slate-200">0.0</span>
                </div>
              </div>

              <div className="bg-slate-900/50 p-5 rounded-xl border border-slate-800">
                <h4 className="text-sm font-semibold text-slate-300 mb-2 uppercase tracking-wide">AI Feedback</h4>
                <p className="text-slate-300 leading-relaxed">
                  {finalResult.feedback}
                </p>
              </div>
            </Card>
          )}

        </div>
      </div>
    </div>
  );
}
