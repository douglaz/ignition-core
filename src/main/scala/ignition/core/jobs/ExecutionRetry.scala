package ignition.core.jobs

import scala.util.Try

trait ExecutionRetry {

  def executeRetrying[T](code: => T, maxExecutions: Int = 3): T = {
    assert(maxExecutions > 0) // we will execute at least once
    // TODO: log retries

    def _executeRetrying(retriesLeft: Int): Try[T] = {
      val tryResult = Try { code }
      if (tryResult.isFailure && retriesLeft > 0) {
        _executeRetrying(retriesLeft - 1)
      } else {
        tryResult
      }
    }

    _executeRetrying(maxExecutions - 1).get
  }

}
