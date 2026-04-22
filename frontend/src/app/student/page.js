"use client";

import React, { useMemo, useState } from "react";
import Link from "next/link";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import Card from "@/components/Card";
import Button from "@/components/Button";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchWithApiFallback(path, options = {}) {
  return fetch(`${API_BASE}${path}`, options);
}

function SegmentedBar({ total, value, activeClass = "bg-cyan-500", baseClass = "bg-slate-800" }) {
  return (
    <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${total}, minmax(0, 1fr))` }}>
      {Array.from({ length: total }).map((_, idx) => (
        <div
          key={idx}
          className={`h-2 rounded-full ${idx < value ? activeClass : baseClass}`}
        />
      ))}
    </div>
  );
}

function QuestionStatBlock({ item }) {
  const relevancePct = Math.round((item.scores?.relevance_r || 0) * 100);


  return (
    <div className="mt-4 rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="flex-1 space-y-3">
          <div>
            <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Relevance</p>
            <div className="h-2 w-full rounded-full bg-slate-800">
              <div
                className="h-2 rounded-full bg-cyan-500"
                style={{ width: `${relevancePct}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-slate-400">{item.scores?.relevance_r}</p>
          </div>

          <div>
            <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Bloom&apos;s</p>
            <SegmentedBar total={6} value={item.scores?.bloom_b || 0} activeClass="bg-violet-500" />
          </div>

          <div>
            <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Depth</p>
            <SegmentedBar total={4} value={item.scores?.depth_d || 0} activeClass="bg-emerald-500" />
          </div>
        </div>

        <div className="mx-auto flex h-28 w-28 shrink-0 items-center justify-center rounded-full border-4 border-cyan-500/60 bg-cyan-500/10 text-center shadow-lg shadow-cyan-500/10 md:mx-0">
          <div>
            <p className="text-[10px] uppercase tracking-wide text-cyan-300">Question Score</p>
            <p className="text-2xl font-black text-cyan-200">{item.question_score}</p>
          </div>
        </div>
      </div>

      {item.scores?.bridging_bonus === 1 && (
        <div className="mt-3 inline-flex items-center rounded-full border border-emerald-400/50 bg-emerald-500/20 px-3 py-1 text-xs font-semibold text-emerald-200 animate-pulse">
          🌟 +1 Bridging Bonus
        </div>
      )}


    </div>
  );
}

function TestKey({ materials }) {
  if (!materials?.length) {
    return (
      <Card className="border border-emerald-400/20 bg-slate-950/70 md:sticky md:top-4">
        <p className="text-xs uppercase tracking-[0.2em] text-emerald-300">Test Key</p>
        <p className="mt-3 text-sm text-slate-400">No document outline is available for this test yet.</p>
      </Card>
    );
  }

  return (
    <Card className="border border-emerald-400/30 bg-slate-950/75 shadow-[0_0_30px_rgba(16,185,129,0.12)] md:sticky md:top-4">
      <p className="text-xs uppercase tracking-[0.2em] text-emerald-300">Test Key</p>
      <p className="mt-2 text-sm text-slate-300">Topics expected from the uploaded documents.</p>

      <div className="mt-5 space-y-5">
        {materials.map((material) => (
          <div key={material.id} className="rounded-2xl border border-emerald-400/15 bg-emerald-500/5 p-4">
            <p className="text-sm font-semibold text-white">{material.file_name}</p>
            <p className="mt-1 text-xs uppercase tracking-wide text-emerald-200/80">
              {material.topic_outline?.length ? "Topic outline" : "No extracted outline"}
            </p>

            {material.topic_outline?.length ? (
              <ul className="mt-3 space-y-2">
                {material.topic_outline.map((topic) => (
                  <li key={topic} className="flex items-start gap-3 text-sm text-emerald-100">
                    <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-emerald-400 shadow-[0_0_14px_rgba(74,222,128,0.95)]" />
                    <span>{topic}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-slate-400">
                The document was uploaded, but no clear sub-headings were extracted.
              </p>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function archetypeFromAverages(avgR, avgB, avgD) {
  if (avgB >= 5) return "The Visionary";
  if (avgD >= 3.5 && avgR >= 0.75) return "The Sage";
  if (avgR <= 0.5 && avgB >= 4) return "The Explorer";
  return "The Novice";
}

export default function StudentPage() {
  const [stage, setStage] = useState("lobby");
  const [studentName, setStudentName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [subjectName, setSubjectName] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [questionQuota, setQuestionQuota] = useState(0);
  const [questionsAsked, setQuestionsAsked] = useState(0);
  const [testMaterials, setTestMaterials] = useState([]);

  const [questionText, setQuestionText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isLoadingReport, setIsLoadingReport] = useState(false);
  const [statusLine, setStatusLine] = useState("");
  const [error, setError] = useState("");

  const [activeStreamingFeedback, setActiveStreamingFeedback] = useState("");
  const [feedbackCards, setFeedbackCards] = useState([]);
  const [report, setReport] = useState(null);

  const cumulativeScore = useMemo(
    () => feedbackCards.reduce((sum, card) => sum + (Number(card.question_score) || 0), 0),
    [feedbackCards]
  );

  const reportAverages = useMemo(() => {
    if (!report?.questions?.length) {
      return { avgR: 0, avgB: 0, avgD: 0 };
    }
    const count = report.questions.length;
    const avgR = report.questions.reduce((s, q) => s + (q.r_score || 0), 0) / count;
    const avgB = report.questions.reduce((s, q) => s + (q.b_score || 0), 0) / count;
    const avgD = report.questions.reduce((s, q) => s + (q.d_score || 0), 0) / count;
    return { avgR, avgB, avgD };
  }, [report]);

  const radarData = useMemo(() => {
    const { avgR, avgB, avgD } = reportAverages;
    return [
      { metric: "Relevance", score: Math.round(avgR * 100) },
      { metric: "Bloom", score: Math.round((avgB / 6) * 100) },
      { metric: "Depth", score: Math.round((avgD / 4) * 100) },
    ];
  }, [reportAverages]);

  const startAssessment = async () => {
    setError("");
    if (!studentName.trim() || !joinCode.trim()) {
      setError("Please enter your name and test join code.");
      return;
    }

    setIsStarting(true);
    try {
      const res = await fetchWithApiFallback("/api/sessions/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          student_name: studentName.trim(),
          test_id: joinCode.trim(),
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || "Could not start session.");
      }

      setSessionId(data.session_id);
      setSubjectName(data.subject_name);
      setQuestionQuota(data.question_quota);
      setTestMaterials(data.materials || []);
      setQuestionsAsked(0);
      setFeedbackCards([]);
      setReport(null);
      setStage("active");
    } catch (err) {
      setError(err.message || "Could not start assessment.");
    } finally {
      setIsStarting(false);
    }
  };

  const loadFinalReport = async (targetSessionId) => {
    setIsLoadingReport(true);
    try {
      const res = await fetchWithApiFallback(`/api/sessions/${targetSessionId}/report`);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || "Could not load final report.");
      }
      setReport(data);
      setStage("final");
    } catch (err) {
      setError(err.message || "Could not load final report.");
    } finally {
      setIsLoadingReport(false);
    }
  };

  const submitQuestion = async (e) => {
    e.preventDefault();
    if (!questionText.trim() || isSubmitting || questionsAsked >= questionQuota) {
      return;
    }

    setIsSubmitting(true);
    setError("");
    setStatusLine("Submitting question...");
    setActiveStreamingFeedback("");

    const currentQuestion = questionText.trim();

    try {
      const response = await fetchWithApiFallback("/api/submit-question", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          test_id: joinCode.trim(),
          session_id: sessionId,
          student_name: studentName.trim(),
          question_text: currentQuestion,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to evaluate question");
      }

      const data = await response.json();
      
      const newAskedCount = questionsAsked + 1;
      setQuestionsAsked(newAskedCount);
      
      setFeedbackCards((prev) => [
        {
          question: currentQuestion,
          question_score: data.scores?.composite_score,
          scores: data.scores,
          feedback: data.feedback,
          scaffold_strategy: data.scaffold_strategy,
          session_stats: data.session_stats
        },
        ...prev,
      ]);

      setQuestionText("");
      setStatusLine("Evaluation complete.");

      if (newAskedCount >= questionQuota) {
        await loadFinalReport(sessionId);
      }
    } catch (err) {
      setError(err.message || "Failed to evaluate question.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const resetToLobby = () => {
    setStage("lobby");
    setQuestionText("");
    setSessionId("");
    setSubjectName("");
    setQuestionQuota(0);
    setQuestionsAsked(0);
    setTestMaterials([]);
    setFeedbackCards([]);
    setReport(null);
    setStatusLine("");
    setError("");
  };

  if (stage === "lobby") {
    return (
      <div className="min-h-screen p-6 md:p-12 flex items-center justify-center">
        <Card className="w-full max-w-2xl border border-slate-800 bg-slate-900/80">
          <h1 className="text-3xl font-bold text-white">Assessment Lobby</h1>
          <p className="mt-2 text-slate-400">Enter your details to begin the test.</p>

          <div className="mt-6 space-y-4">
            <div>
              <label className="mb-1 block text-sm text-slate-300">Student Name</label>
              <input
                value={studentName}
                onChange={(e) => setStudentName(e.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-slate-100 outline-none focus:border-cyan-500"
                placeholder="Your name"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-300">Test Join Code</label>
              <input
                value={joinCode}
                onChange={(e) => setJoinCode(e.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-slate-100 outline-none focus:border-cyan-500"
                placeholder="Paste UUID code from faculty"
              />
            </div>
          </div>

          {error && <p className="mt-4 text-sm text-rose-300">{error}</p>}

          <div className="mt-6 flex items-center justify-between">
            <Link href="/" className="text-sm text-slate-400 hover:text-white">Back to Home</Link>
            <Button type="button" disabled={isStarting} onClick={startAssessment}>
              {isStarting ? "Starting..." : "Start Assessment"}
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  if (stage === "final") {
    const { avgR, avgB, avgD } = reportAverages;
    const archetype = archetypeFromAverages(avgR, avgB, avgD);

    return (
      <div className="min-h-screen p-6 md:p-12 max-w-6xl mx-auto">
        <Card className="border border-emerald-500/40 bg-emerald-900/10">
          {isLoadingReport ? (
            <p className="text-slate-200">Loading final report...</p>
          ) : (
            <>
              <p className="text-xs uppercase tracking-[0.2em] text-emerald-300">Curiosity Archetype</p>
              <h1 className="mt-2 text-4xl md:text-6xl font-black text-emerald-300">{archetype}</h1>
              <p className="mt-4 text-2xl md:text-3xl font-bold text-white">
                Final Curiosity Score: {report?.final_clamped_score} / {report?.max_marks}
              </p>
              <p className="mt-2 text-slate-300">Subject: {report?.subject_name}</p>

              <div className="mt-8 h-[320px] w-full rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="#334155" />
                    <PolarAngleAxis dataKey="metric" tick={{ fill: "#cbd5e1", fontSize: 12 }} />
                    <PolarRadiusAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 10 }} />
                    <Radar dataKey="score" stroke="#22d3ee" fill="#22d3ee" fillOpacity={0.35} />
                    <Tooltip />
                  </RadarChart>
                </ResponsiveContainer>
              </div>

              <div className="mt-6 grid grid-cols-1 gap-3 md:grid-cols-3">
                <Card className="border border-slate-700 bg-slate-900/60">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Avg Relevance</p>
                  <p className="mt-1 text-2xl font-bold text-cyan-300">{avgR.toFixed(2)}</p>
                </Card>
                <Card className="border border-slate-700 bg-slate-900/60">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Avg Bloom</p>
                  <p className="mt-1 text-2xl font-bold text-violet-300">{avgB.toFixed(2)}</p>
                </Card>
                <Card className="border border-slate-700 bg-slate-900/60">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Avg Depth</p>
                  <p className="mt-1 text-2xl font-bold text-emerald-300">{avgD.toFixed(2)}</p>
                </Card>
              </div>

              <div className="mt-8 space-y-3">
                {report?.questions?.map((q, idx) => (
                  <details
                    key={idx}
                    className="rounded-xl border border-slate-700 bg-slate-900/70 p-4"
                    open={idx === 0}
                  >
                    <summary className="cursor-pointer text-slate-100">Question {idx + 1}</summary>
                    <p className="mt-3 text-sm text-slate-200">{q.question_text}</p>
                    <QuestionStatBlock
                      item={{
                        question_score: q.final_question_score,
                        scores: {
                          relevance_r: q.r_score,
                          bloom_b: q.b_score,
                          depth_d: q.d_score,
                          bridging_bonus: q.bridging_bonus,
                        },
                        penalties_applied: q.penalties_applied,
                      }}
                    />
                    <p className="mt-3 text-sm text-slate-300">{q.feedback}</p>
                  </details>
                ))}
              </div>
            </>
          )}

          <div className="mt-8">
            <Button type="button" onClick={resetToLobby}>Back to Lobby</Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full px-3 py-6 sm:px-5 md:px-6 lg:px-4 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Active Assessment</h1>
          <p className="text-slate-400">{subjectName} | Session: {sessionId}</p>
        </div>
        <Link href="/" className="text-sm text-slate-400 hover:text-white">Back to Home</Link>
      </div>

      <div className="sticky top-4 z-20 rounded-2xl border border-cyan-500/40 bg-slate-900/90 px-4 py-3 shadow-lg shadow-cyan-500/10 backdrop-blur">
        <p className="text-sm font-medium text-cyan-200">
          Questions: {questionsAsked} / {questionQuota} | Cumulative Score: {cumulativeScore.toFixed(2)}
        </p>
      </div>

      <div className="grid items-start gap-8 lg:gap-x-24 lg:grid-cols-[260px_700px]">
        <TestKey materials={testMaterials} />

        <div className="w-full max-w-[700px] space-y-6">
          <Card className="w-full">
            <form onSubmit={submitQuestion} className="space-y-4">
              <textarea
                value={questionText}
                onChange={(e) => setQuestionText(e.target.value)}
                placeholder="Ask your next question..."
                className="w-full h-[300px] max-w-[700px] resize-none rounded-xl border border-slate-700 bg-slate-950 p-4 text-slate-100 outline-none focus:border-cyan-500"
                disabled={isSubmitting || questionsAsked >= questionQuota}
              />
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">{statusLine}</span>
                <Button type="submit" disabled={isSubmitting || questionsAsked >= questionQuota}>
                  {isSubmitting ? "Evaluating..." : "Submit Question"}
                </Button>
              </div>
            </form>

            {activeStreamingFeedback && (
              <div className="mt-3 rounded-xl border border-cyan-500/40 bg-cyan-500/10 p-3 text-sm text-cyan-200">
                {activeStreamingFeedback}
              </div>
            )}

            {error && <p className="mt-3 text-sm text-rose-300">{error}</p>}
          </Card>

          <div className="w-full max-w-[700px] space-y-4">
            {feedbackCards.map((item, idx) => (
              <Card
                key={`${item.session_id}-${idx}`}
                className="w-full max-w-[700px] border border-slate-700 bg-slate-900/70 shadow-xl shadow-slate-950/50"
              >
                <p className="text-xs uppercase tracking-wide text-slate-500">Student Question</p>
                <p className="mt-1 text-slate-100">{item.question}</p>

                <p className="mt-4 text-xs uppercase tracking-wide text-slate-500">Empathetic Feedback</p>
                <p className="mt-1 text-slate-200">{item.feedback}</p>

                <QuestionStatBlock item={item} />
              </Card>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
