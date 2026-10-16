"""
Command Line Interface for Judges & Automated Evaluation Scorer.
Executes synchronous segmentation inference directly from the terminal.

Usage:
  python -m app.cli predict --t1 <file> --t1gd <file> --t2 <file> --flair <file> --out <out.nii.gz>
"""
import sys
import argparse
from pathlib import Path
from app.validation import validate_set, ValidationError
from ml.predict import Segmenter


def main():
    parser = argparse.ArgumentParser(
        description="NeuroScope 3D Judges Evaluation CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    predict_parser = subparsers.add_parser("predict", help="Run brain MRI segmentation inference")
    predict_parser.add_argument("--t1", required=True, type=str, help="Path to T1-weighted NIfTI")
    predict_parser.add_argument("--t1gd", required=True, type=str, help="Path to T1-Gd contrast NIfTI")
    predict_parser.add_argument("--t2", required=True, type=str, help="Path to T2-weighted NIfTI")
    predict_parser.add_argument("--flair", required=True, type=str, help="Path to FLAIR NIfTI")
    predict_parser.add_argument("--out", required=True, type=str, help="Destination path for predicted .nii.gz mask")
    
    args = parser.parse_args()
    
    if args.command == "predict":
        paths = {
            "t1": Path(args.t1),
            "t1gd": Path(args.t1gd),
            "t2": Path(args.t2),
            "flair": Path(args.flair)
        }
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            print("1. Validating sequence inputs...")
            validate_set(paths)
            
            print("2. Initializing Segmenter model...")
            segmenter = Segmenter()
            if hasattr(segmenter, "warmup"):
                segmenter.warmup()
                
            print(f"3. Running inference -> {out_path}...")
            segmenter.predict(paths, str(out_path))
            
            if not out_path.exists():
                print("Error: Output prediction was not generated.", file=sys.stderr)
                sys.exit(1)
                
            print(f"SUCCESS: Predicted label mask saved at {out_path}")
            sys.exit(0)
            
        except ValidationError as ve:
            print(f"Validation Error [{ve.code}]: {ve.message}", file=sys.stderr)
            sys.exit(2)
        except Exception as e:
            print(f"Execution Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
