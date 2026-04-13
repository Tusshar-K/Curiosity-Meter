import Link from "next/link";

export default function Home() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-8 text-center">
      <div className="max-w-2xl">
        <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight mb-4">
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-500">
            Curiosity Meter
          </span>
        </h1>
        <p className="text-lg md:text-xl text-slate-300 mb-10 leading-relaxed">
          The AI-driven educational assessment platform that evaluates the depth and quality of questions, rather than just answers.
        </p>
        
        <div className="flex flex-col sm:flex-row gap-6 justify-center items-center">
          <Link href="/faculty" className="w-full sm:w-auto px-8 py-4 rounded-xl bg-blue-600 hover:bg-blue-500 transition-all shadow-lg hover:shadow-blue-500/25 font-semibold text-lg transform hover:-translate-y-1">
            Faculty Ingestion
          </Link>
          <Link href="/student" className="w-full sm:w-auto px-8 py-4 rounded-xl glass hover:bg-slate-800 transition-all border border-slate-700 font-semibold text-lg transform hover:-translate-y-1">
            Student Assessment
          </Link>
        </div>
      </div>
      
      {/* Decorative background shapes */}
      <div className="fixed top-[-10%] left-[-10%] w-96 h-96 bg-blue-600 rounded-full mix-blend-multiply filter blur-[128px] opacity-20 -z-10 animate-blob"></div>
      <div className="fixed top-[20%] right-[-10%] w-96 h-96 bg-purple-600 rounded-full mix-blend-multiply filter blur-[128px] opacity-20 -z-10 animate-blob animation-delay-2000"></div>
    </div>
  );
}
