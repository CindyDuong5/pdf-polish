// frontend/src/App.tsx
import { Routes, Route } from "react-router-dom";
import MainApp from "./MainApp";
import ReviewPage from "./pages/ReviewPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<MainApp />} />
      <Route path="/review" element={<ReviewPage />} />
    </Routes>
  );
}