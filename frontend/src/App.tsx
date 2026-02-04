import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Home from "./pages/Home";
import StudyList from "./pages/StudyList";
import UploadStudy from "./pages/UploadStudy";
import StudyDetail from "./pages/StudyDetail";
import CTStudyList from "./pages/CTStudyList";
import CTUpload from "./pages/CTUpload";
import CTStudyDetail from "./pages/CTStudyDetail";
import TEPStudyList from "./pages/TEPStudyList";
import TEPUpload from "./pages/TEPUpload";
import TEPStudyDetail from "./pages/TEPStudyDetail";
import WorkstationPage from "./pages/WorkstationPage";
import UnifiedUploadPage from "./pages/UnifiedUploadPage";
import UnifiedStudyList from "./pages/UnifiedStudyList";
import ArchitectureDiagram from "./pages/ArchitectureDiagram";

function App() {
	return (
		<Routes>
			{/* ═══════════════════════════════════════════════════════════════════════
          RADIOMIC TENSORIAL WORKSTATION - New unified interface
          ═══════════════════════════════════════════════════════════════════════ */}
			<Route path="/workstation/:studyId" element={<WorkstationPage />} />
			<Route path="/upload" element={<UnifiedUploadPage />} />
			<Route path="/studies" element={<UnifiedStudyList />} />
			<Route path="/architecture" element={<ArchitectureDiagram />} />

			{/* Root redirect to unified study list */}
			<Route path="/" element={<Navigate to="/studies" replace />} />

			{/* ═══════════════════════════════════════════════════════════════════════
          Legacy Routes (with Layout wrapper) - Keep for backwards compatibility
          ═══════════════════════════════════════════════════════════════════════ */}
			<Route path="/legacy" element={<Layout />}>
				<Route index element={<Home />} />
				{/* MRI Routes */}
				<Route path="mri/studies" element={<StudyList />} />
				<Route path="mri/upload" element={<UploadStudy />} />
				<Route path="mri/studies/:id" element={<StudyDetail />} />
				{/* CT Brain Ischemia Routes */}
				<Route path="ct/studies" element={<CTStudyList />} />
				<Route path="ct/upload" element={<CTUpload />} />
				<Route path="ct/studies/:id" element={<CTStudyDetail />} />
				{/* TEP (Pulmonary Embolism) Routes */}
				<Route path="tep/studies" element={<TEPStudyList />} />
				<Route path="tep/upload" element={<TEPUpload />} />
				<Route path="tep/studies/:id" element={<TEPStudyDetail />} />
			</Route>
		</Routes>
	);
}

export default App;
