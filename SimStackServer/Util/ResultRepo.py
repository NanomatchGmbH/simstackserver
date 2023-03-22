from typing import Iterable
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from sqlalchemy import create_engine, select, Text, String
from pathlib import Path
import logging
import hashlib
import shutil


hash_algorithm = hashlib.md5
hash_sql_type = String(32) # should equal `len(hash_algorithm().hexdigest())`
block_size = 8192  # number of bytes to read at a time during file hashing


class Base(DeclarativeBase):
    pass


class Result(Base):
    __tablename__ = "result"
    id: Mapped[int] = mapped_column(primary_key=True)
    input_hash: Mapped[str] = mapped_column(
        hash_sql_type, unique=True, index=True)
    output_hash: Mapped[str] = mapped_column(hash_sql_type)
    output_directory: Mapped[str] = mapped_column(Text())

    def __repr__(self) -> str:
        return f"Result(id={self.id!r}, \
            input_hash={self.input_hash!r}, \
            output_hash={self.output_hash!r}, \
            output_directory={self.output_directory!r})"


def get_wfem_repr(wfem):
    return wfem.outputpath


def compute_files_hash(files: Iterable[Path], base_dir: Path):
    """
    Compute the aggregate hash of a set of files consisting of their content and paths relative to base_dir.
    """
    hash = hash_algorithm()
    for path in files:
        if path.is_file():
            with open(path, "rb") as f:
                while chunk := f.read(block_size):
                    hash.update(chunk)

            rel_path = path.relative_to(base_dir)
            hash.update(bytes(str(rel_path), 'utf-8'))
    return hash


def list_files(dir: Path):
    return sorted(dir.rglob("*"))  # use sorted to ensure deterministic hash


def compute_dir_hash(dir: Path):
    return compute_files_hash(list_files(dir), dir)


class ResultRepo:
    """
    Keeps track of the location of WaNo outputs in the filesytem 
    and allows them to be retrieved to avoid repeated computation of the same result.
    """

    def __init__(self):
        self._logger = logging.getLogger("ResultRepo")
        self._engines = {}

    def _get_engine(self, basepath):
        # TODO check if we can use a single database.
        if basepath in self._engines:
            return self._engines[basepath]
        else:
            absolute_basepath = Path.home() / basepath
            sql_path = f"sqlite:///{absolute_basepath}/result_repo.sqlite"
            self._logger.info(
                f"[REPO] Creating new engine to connect to '{sql_path}'")
            engine = create_engine(sql_path, echo=True)
            Base.metadata.create_all(engine)
            self._engines[basepath] = engine
            return engine

    def compute_input_hash(self, wfem):
        """
        Compute the hash of a WorkflowExecModule. The hash includes:
            - the content of all files in the WFEM's runtime_directory
            - the relative paths of said files within the runtime_directory
            - the WFEM's outputpath field (i.e. AdvancedForEach/9/Branch/True/MyWano)

            The reason for including the outputpath is due to WFEM's that do random sampling,
            meaning they produce different outputs for the same input.

        Args:
            wfem (WorkFlowExecModule)

        Returns:
            str: hash
        """
        runtime_directory = Path(wfem.runtime_directory)

        hash = compute_dir_hash(runtime_directory)
        hash.update(bytes(wfem.outputpath, 'utf-8'))

        return hash.hexdigest()

    def load_results(self, input_hash: str, wfem) -> bool:
        """
        Look for an existing result for the given WFEM and place the output files in the exec_directory if a suitable result was found.

        Args:
            input_hash (str): the initial hash of the WFEM before it has done any computations
            wfem (WorkflowExecModule) 

        Returns:
            bool: True if a suitable result was found. False if no result was found in the database, 
                the files no longer exist in the filesystem or the files no longer match the output_hash saved in the database.
        """
        engine = self._get_engine(wfem.resources.basepath)

        with Session(engine) as session:
            existing_solution = session.scalar(
                select(Result).where(Result.input_hash == input_hash))

        if existing_solution is None:
            self._logger.info(f"[REPO] Did not find existing solution for {get_wfem_repr(wfem)} with hash {input_hash}. \
                              Results will be re-computed.")
            return False

        source_dir = Path.home() / wfem.resources.basepath / Path(existing_solution.output_directory)
        target_dir = Path(wfem.runtime_directory)

        if not source_dir.exists():
            self._logger.warning(
                f"[REPO] Result directory {source_dir} could not be found. Results will be re-computed.")
            return False

        self._logger.info(
            f"[REPO] Found existing solution for {get_wfem_repr(wfem)} with hash {input_hash} in {source_dir}")

        # Ensure the files have not changed after the result was stored in the database
        source_hash = compute_dir_hash(source_dir).hexdigest()

        if source_hash != existing_solution.output_hash:
            self._logger.warning(f"[REPO] One or multiple files in {source_dir} appear to have changed. \
                                 Results will be re-computed.")
            return False

        self._logger.info(f"[REPO] Files will be copied from {source_dir} to {target_dir}")
        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
        return True

    def store_results(self, input_hash: str, wfem):
        """
        Create an entry in the result database with a reference to the output directory of the WFEM.
        If an entry with the same hash already exists, it will be overwritten.

        Args:
            input_hash (str): the initial hash of the WFEM before it has done any computations.
            wfem (WorkFlowExecModule)
        """
        source_dir = Path(wfem.runtime_directory)
        base_path = Path.home() / wfem.resources.basepath
        with open(source_dir / "original_job.txt", "w") as f:
            f.write(f"original job path: {source_dir}")

        output_hash = compute_dir_hash(source_dir).hexdigest()

        engine = self._get_engine(wfem.resources.basepath)

        result = Result(
            input_hash=input_hash,
            output_hash=output_hash,
            output_directory=str(source_dir.relative_to(base_path)),
        )

        with Session(engine) as session:
            # overwrite existing result
            existing_result = session.scalar(
                select(Result).where(Result.input_hash == input_hash))
            if existing_result is not None:
                result.id = existing_result.id

            session.merge(result)
            session.commit()
        self._logger.info(f"[REPO] Stored results of {get_wfem_repr(wfem)} with hash {input_hash}.")