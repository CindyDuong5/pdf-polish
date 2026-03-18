// frontend/src/App.tsx
import { Routes, Route } from "react-router-dom";
import MainApp from "./pages/MainApp";
import ReviewPage from "./pages/ReviewPage";
import DocumentHistoryPage from "./pages/DocumentHistoryPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<MainApp />} />
      <Route path="/review" element={<ReviewPage />} />
      <Route path="/history" element={<DocumentHistoryPage />} />
    </Routes>
  );
}