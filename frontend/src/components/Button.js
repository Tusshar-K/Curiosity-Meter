export default function Button({ children, onClick, variant = "primary", className = "", disabled=false }) {
  const baseStyles = "px-6 py-3 rounded-xl font-medium transition-all transform active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed";
  
  const variants = {
    primary: "bg-blue-600 hover:bg-blue-500 shadow-lg hover:shadow-blue-500/25 text-white",
    secondary: "bg-slate-800 hover:bg-slate-700 border border-slate-600 text-white",
    ghost: "hover:bg-slate-800/50 text-slate-300 hover:text-white"
  };

  return (
    <button 
      onClick={onClick} 
      className={`${baseStyles} ${variants[variant] || variants.primary} ${className}`}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
