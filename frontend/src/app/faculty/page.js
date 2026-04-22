"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Card from "@/components/Card";
import Button from "@/components/Button";

const defaultRules = {
	question_quota: 5,
	max_marks: 50,
};

function SoftToggle({ checked, onChange, label }) {
	return (
		<button
			type="button"
			onClick={() => onChange(!checked)}
			className={`w-full rounded-xl border px-4 py-3 text-left transition ${
				checked
					? "border-emerald-500/40 bg-emerald-500/10"
					: "border-slate-700 bg-slate-900/70"
			}`}
		>
			<div className="flex items-center justify-between">
				<span className="text-sm font-medium text-slate-200">{label}</span>
				<span
					className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${
						checked ? "bg-emerald-500" : "bg-slate-600"
					}`}
				>
					<span
						className={`inline-block h-5 w-5 transform rounded-full bg-white transition ${
							checked ? "translate-x-5" : "translate-x-1"
						}`}
					/>
				</span>
			</div>
		</button>
	);
}

export default function FacultyPage() {
	const [isProcessing, setIsProcessing] = useState(false);
	const [isLoadingTests, setIsLoadingTests] = useState(false);
	const [showRules, setShowRules] = useState(false);
	const [success, setSuccess] = useState(false);
	const [error, setError] = useState("");
	const [copied, setCopied] = useState(false);
	const [ingestResult, setIngestResult] = useState(null);
	const [tests, setTests] = useState([]);
	const [file, setFile] = useState(null);
	const fileInputRef = useRef(null);
	const [subjectName, setSubjectName] = useState("MECH 301");
	const [rules, setRules] = useState(defaultRules);

	const updateRule = (key, value) => {
		setRules((prev) => ({ ...prev, [key]: value }));
	};

	const removeSelectedFile = () => {
		setFile(null);
		if (fileInputRef.current) {
			fileInputRef.current.value = "";
		}
	};

	const fetchCreatedTests = async () => {
		setIsLoadingTests(true);
		try {
			let response = null;
			
			const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
            response = await fetch(`${API_BASE}/api/ingest/tests`);		
			if (!response.ok) {
				throw new Error("Failed to fetch tests");
			}

			const data = await response.json();
			setTests(data.tests || []);
		} catch (err) {
			console.error("Failed to fetch created tests", err);
		} finally {
			setIsLoadingTests(false);
		}
	};

	useEffect(() => {
		fetchCreatedTests();
	}, []);

	const handleDeleteTest = async (testId) => {
		if (!confirm("Are you sure you want to delete this test? All student sessions and grades will be lost.")) return;
		
		try {
			let response = null;
			const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
			response = await fetch(`${API_BASE}/api/ingest/tests/${testId}`, { method: "DELETE" });
			
			if (!response.ok) {
				throw new Error("Failed to delete test");
			}
			
			fetchCreatedTests();
		} catch (err) {
			console.error("Failed to delete test", err);
			alert("Failed to delete test");
		}
	};

	const handleSubmit = async (e) => {
		e.preventDefault();
		setError("");
		setSuccess(false);
		setCopied(false);
		setIngestResult(null);

		if (!subjectName.trim()) {
			setError("Subject name is required.");
			return;
		}
		if (!file) {
			setError("Please upload a PDF file.");
			return;
		}

		setIsProcessing(true);

		try {
			const formData = new FormData();
			formData.append("file", file);
			formData.append("faculty_name", "Faculty Demo");
			formData.append("subject_name", subjectName.trim());
			formData.append("question_quota", String(Math.max(1, Number(rules.question_quota) || 5)));
			formData.append("max_marks", String(Math.max(1, Number(rules.max_marks) || 50)));

			const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
			const res = await fetch(`${API_BASE}/api/ingest`, {
				method: "POST",
				body: formData,
			});

			const data = await res.json();
			if (!res.ok) {
				throw new Error(data?.detail || "Upload failed.");
			}

			setIngestResult(data);
			setSuccess(true);
			removeSelectedFile();
			fetchCreatedTests();
		} catch (err) {
			setError(err.message || "Could not ingest file.");
		} finally {
			setIsProcessing(false);
		}
	};

	const copyJoinCode = async () => {
		if (!ingestResult?.test_id) {
			return;
		}
		try {
			await navigator.clipboard.writeText(ingestResult.test_id);
			setCopied(true);
			setTimeout(() => setCopied(false), 1800);
		} catch {
			setError("Unable to copy code. Please copy it manually.");
		}
	};

	return (
		<div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 p-6 md:p-12">
			<div className="mx-auto w-full max-w-4xl">
				<div className="mb-8 flex items-center justify-between">
					<div>
						<h1 className="text-3xl font-bold tracking-tight text-slate-100">Faculty Ingestion</h1>
						<p className="mt-1 text-sm text-slate-400">Create a test and upload one source PDF.</p>
					</div>
					<Link href="/" className="text-sm text-slate-400 transition hover:text-slate-100">
						Back to Home
					</Link>
				</div>

				<Card className="border border-slate-800 bg-slate-900/70 shadow-2xl shadow-slate-950/40">
					<form onSubmit={handleSubmit} className="space-y-6">
						<div className="space-y-2">
							<label className="text-sm font-medium text-slate-200">Subject Name</label>
							<input
								type="text"
								value={subjectName}
								onChange={(e) => setSubjectName(e.target.value)}
								placeholder="MECH 301"
								className="w-full rounded-xl border border-slate-700 bg-slate-950/60 px-4 py-3 text-slate-100 outline-none transition focus:border-cyan-500"
								disabled={isProcessing}
							/>
						</div>

						<div className="space-y-2">
							<label className="text-sm font-medium text-slate-200">PDF Material</label>
							<label
								htmlFor="file-upload"
								className="block cursor-pointer rounded-2xl border-2 border-dashed border-slate-700 bg-slate-950/50 p-10 text-center transition hover:border-cyan-500/60 hover:bg-slate-900"
							>
								<div className="mx-auto max-w-sm">
									<p className="text-base font-medium text-slate-200">Drop PDF here or click to upload</p>
									<p className="mt-1 text-xs text-slate-500">Single PDF, up to 50MB</p>
								</div>
								<input
									id="file-upload"
									ref={fileInputRef}
									type="file"
									accept=".pdf"
									className="hidden"
									onChange={(e) => setFile(e.target.files?.[0] || null)}
									disabled={isProcessing}
								/>
							</label>
							{file && (
								<div className="flex items-center justify-between rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-sm text-cyan-200">
									<span className="truncate pr-3">Selected: {file.name}</span>
									<button
										type="button"
										onClick={removeSelectedFile}
										disabled={isProcessing}
										className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 transition hover:border-rose-400 hover:text-rose-300 disabled:opacity-50"
									>
										Remove
									</button>
								</div>
							)}
						</div>

						<div className="rounded-2xl border border-slate-700 bg-slate-950/50">
							<button
								type="button"
								onClick={() => setShowRules((s) => !s)}
								className="flex w-full items-center justify-between px-4 py-3 text-left"
							>
								<div>
									<p className="text-sm font-semibold text-slate-200">⚙️ Test Rules & Scoring (Defaults Applied)</p>
									<p className="text-xs text-slate-500">Optional settings. Safe defaults are already enabled.</p>
								</div>
								<span className="text-slate-400">{showRules ? "Hide" : "Show"}</span>
							</button>

							{showRules && (
								<div className="grid gap-4 border-t border-slate-800 p-4 md:grid-cols-2">
									<div className="space-y-2">
										<label className="text-xs font-medium uppercase tracking-wide text-slate-400">Question Quota</label>
										<input
											type="number"
											min="1"
											value={rules.question_quota}
											onChange={(e) => updateRule("question_quota", e.target.value)}
											className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-cyan-500"
										/>
									</div>

									<div className="space-y-2">
										<label className="text-xs font-medium uppercase tracking-wide text-slate-400">Maximum Marks</label>
										<input
											type="number"
											min="1"
											value={rules.max_marks}
											onChange={(e) => updateRule("max_marks", e.target.value)}
											className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-cyan-500"
										/>
									</div>


								</div>
							)}
						</div>

						<div className="flex items-center justify-end gap-3">
							<Button type="submit" disabled={isProcessing}>
								<span className="inline-flex items-center gap-2">
									{isProcessing && (
										<span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-transparent" />
									)}
									{isProcessing ? "Chunking & Embedding..." : "Create Test"}
								</span>
							</Button>
						</div>
					</form>

					{error && (
						<div className="mt-5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
							{error}
						</div>
					)}

					{success && ingestResult && (
						<div className="mt-5 rounded-2xl border border-emerald-500/40 bg-emerald-500/10 px-5 py-5">
							<p className="text-sm font-semibold uppercase tracking-wide text-emerald-300">Test Created Successfully</p>
							<p className="mt-3 text-xs text-slate-400">Test Join Code</p>
							<div className="mt-2 flex items-center gap-3">
								<p className="flex-1 break-all rounded-lg border border-emerald-500/40 bg-slate-950/70 px-4 py-3 font-mono text-lg text-emerald-200 md:text-xl">
									{ingestResult.test_id}
								</p>
								<button
									type="button"
									onClick={copyJoinCode}
									className="rounded-lg border border-emerald-500/40 px-3 py-2 text-sm text-emerald-200 transition hover:bg-emerald-500/20"
								>
									{copied ? "Copied" : "Copy to Clipboard"}
								</button>
							</div>
							<p className="mt-3 text-sm text-slate-300">Share this code with your students to access this specific test.</p>
						</div>
					)}

					<div className="mt-6 rounded-2xl border border-slate-700 bg-slate-950/50 p-4">
						<div className="mb-3 flex items-center justify-between">
							<h3 className="text-sm font-semibold text-slate-200">Previously Created Tests</h3>
							<button
								type="button"
								onClick={fetchCreatedTests}
								disabled={isLoadingTests}
								className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 transition hover:border-cyan-500 hover:text-cyan-300 disabled:opacity-50"
							>
								{isLoadingTests ? "Refreshing..." : "Refresh"}
							</button>
						</div>

						{tests.length === 0 ? (
							<p className="text-sm text-slate-500">No tests created yet.</p>
						) : (
							<ul className="space-y-3">
								{tests.map((test) => (
									<li key={test.id} className="relative rounded-xl border border-slate-800 bg-slate-900/70 p-3">
										<div className="absolute right-3 top-3">
											<button
												onClick={() => handleDeleteTest(test.id)}
												className="rounded-md border border-slate-600 px-2 py-1 text-xs text-rose-400 transition hover:bg-rose-500/10 hover:border-rose-400 focus:outline-none"
											>
												Remove
											</button>
										</div>
										<p className="text-sm font-medium text-slate-100 pr-16">{test.subject_name}</p>
										<p className="mt-1 break-all text-xs text-slate-400">Test ID: {test.id}</p>
										<p className="mt-2 text-xs font-medium uppercase tracking-wide text-slate-500">Files</p>
										{test.materials && test.materials.length > 0 ? (
											<ul className="mt-1 space-y-1">
												{test.materials.map((material) => (
													<li key={material.id} className="text-xs text-slate-300">
														- {material.file_name}
													</li>
												))}
											</ul>
										) : (
											<p className="mt-1 text-xs text-slate-500">No files attached.</p>
										)}
									</li>
								))}
							</ul>
						)}
					</div>
				</Card>
			</div>
		</div>
	);
}
