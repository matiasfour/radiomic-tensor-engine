import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";
import type { Study, ROIStats, RoiData } from "../types";

export const api = createApi({
	reducerPath: "api",
	baseQuery: fetchBaseQuery({ baseUrl: "http://localhost:8000/api/" }),
	tagTypes: ["Study"],
	endpoints: builder => ({
		getStudies: builder.query<Study[], void>({
			query: () => "studies/",
			providesTags: ["Study"],
		}),
		getStudy: builder.query<Study, string>({
			query: id => `studies/${id}/`,
			providesTags: (_result, _error, id) => [{ type: "Study", id }],
		}),
		createStudy: builder.mutation<Study, FormData>({
			query: formData => ({
				url: "studies/",
				method: "POST",
				body: formData,
			}),
			invalidatesTags: ["Study"],
		}),
		processStudy: builder.mutation<Study, string>({
			query: studyId => ({
				url: `studies/${studyId}/process/`,
				method: "POST",
			}),
			invalidatesTags: (_result, _error, studyId) => [
				{ type: "Study", id: studyId },
			],
		}),
		getROIStats: builder.mutation<ROIStats, { id: string; roiData: RoiData }>({
			query: ({ id, roiData }) => ({
				url: `studies/${id}/roi_stats/`,
				method: "POST",
				body: roiData,
			}),
		}),
		deleteStudy: builder.mutation<void, string>({
			query: id => ({
				url: `studies/${id}/`,
				method: "DELETE",
			}),
			invalidatesTags: ["Study"],
		}),
	}),
});

export const {
	useGetStudiesQuery,
	useGetStudyQuery,
	useCreateStudyMutation,
	useProcessStudyMutation,
	useGetROIStatsMutation,
	useDeleteStudyMutation,
} = api;
