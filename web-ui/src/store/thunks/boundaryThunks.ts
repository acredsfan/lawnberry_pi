import { createAsyncThunk } from '@reduxjs/toolkit';
import { boundaryService, Boundary, BoundaryCreateRequest } from '../../services/boundaryService';

export const fetchBoundaries = createAsyncThunk(
  'mower/fetchBoundaries',
  async (_, { rejectWithValue }) => {
    try {
      const boundaries = await boundaryService.getBoundaries();
      return boundaries;
    } catch (error) {
      return rejectWithValue(error instanceof Error ? error.message : 'Failed to fetch boundaries');
    }
  }
);

export const createBoundary = createAsyncThunk(
  'mower/createBoundary',
  async (boundaryData: BoundaryCreateRequest, { rejectWithValue }) => {
    try {
      const boundary = await boundaryService.createBoundary(boundaryData);
      return boundary;
    } catch (error) {
      return rejectWithValue(error instanceof Error ? error.message : 'Failed to create boundary');
    }
  }
);

export const deleteBoundary = createAsyncThunk(
  'mower/deleteBoundary',
  async (boundaryId: string, { rejectWithValue }) => {
    try {
      await boundaryService.deleteBoundary(boundaryId);
      return boundaryId;
    } catch (error) {
      return rejectWithValue(error instanceof Error ? error.message : 'Failed to delete boundary');
    }
  }
);
